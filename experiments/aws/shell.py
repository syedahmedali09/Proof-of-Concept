'''This is a shell for orchestrating experiments on AWS EC 2'''
import os

from functools import partial
from subprocess import call, check_output
from time import sleep, time
from joblib import Parallel, delayed

import boto3
import numpy as np

from aleph.crypto.keys import SigningKey, VerifyKey
from utils import image_id_in_region, default_region_name, init_key_pair, security_group_id_by_region, available_regions, badger_regions, generate_signing_keys, n_hosts_per_regions, eu_regions
from config import N_JOBS


#======================================================================================
#                              routines for some region
#======================================================================================

def latency_in_region(region_name):
    if region_name == 'default':
        region_name = default_region_name()

    print('finding latency', region_name)

    ip_list = instances_ip_in_region(region_name)
    assert ip_list, 'there are no instances running!'

    reps = 10
    cmd = f'parallel nping -q -c {reps} -p 22 ::: ' + ' '.join(ip_list)
    output = check_output(cmd.split()).decode()
    lines = output.split('\n')
    times = []
    for i in range(len(lines)//5):  # equivalent to range(len(ip_list))
        times_ = lines[5*i+2].split('|')
        times_ = [t.split()[2][:-2] for t in times_]
        times.append([float(t.strip()) for t in times_])

    latency = [f'{round(t, 2)}ms' for t in np.mean(times, 0)]
    latency = dict(zip(['max', 'min', 'avg'], latency))

    return latency


def launch_new_instances_in_region(n_hosts=1, region_name='default', instance_type='t2.micro'):
    '''Launches n_hosts in a given region.'''

    if region_name == 'default':
        region_name = default_region_name()

    print('launching instances in', region_name)

    #print(region_name, 'key init')
    key_name = 'aleph'
    init_key_pair(region_name, key_name)

    #print(region_name, 'sg init')
    security_group_name = 'aleph'
    security_group_id = security_group_id_by_region(region_name, security_group_name)

    #print(region_name, 'image init')
    image_id = image_id_in_region(region_name)

    #print(region_name, 'launch instance')
    ec2 = boto3.resource('ec2', region_name)
    instances = ec2.create_instances(ImageId=image_id,
                                 MinCount=n_hosts, MaxCount=n_hosts,
                                 InstanceType=instance_type,
                                 BlockDeviceMappings=[ {
                                     'DeviceName': '/dev/xvda',
                                     'Ebs': {
                                         'DeleteOnTermination': True,
                                         'VolumeSize': 8,
                                         'VolumeType': 'gp2'
                                     },
                                 }, ],
                                 KeyName=key_name,
                                 Monitoring={ 'Enabled': False },
                                 SecurityGroupIds = [security_group_id])
    #print(region_name, 'done')

    return instances


def terminate_instances_in_region(region_name='default'):
    '''Terminates all running instances in a given regions.'''

    if region_name == 'default':
        region_name = default_region_name()

    print('terminating instances in', region_name)

    ec2 = boto3.resource('ec2', region_name)
    print(region_name, 'terminating')
    for instance in ec2.instances.all():
        instance.terminate()


def all_instances_in_region(region_name='default'):
    '''Returns all running or pending instances in a given region.'''

    if region_name == 'default':
        region_name = default_region_name()

    ec2 = boto3.resource('ec2', region_name)
    instances = []
    print(region_name, 'collecting instances')
    for instance in ec2.instances.all():
        if instance.state['Name'] in ['running', 'pending']:
            instances.append(instance)

    return instances


def instances_ip_in_region(region_name='default'):
    '''Returns ips of all running or pending instances in a given region.'''

    if region_name == 'default':
        region_name = default_region_name()

    ec2 = boto3.resource('ec2', region_name)
    ips = []
    # print(region_name, 'collecting ips')
    for instance in ec2.instances.all():
        if instance.state['Name'] in ['running', 'pending']:
            ips.append(instance.public_ip_address)

    return ips


def instances_state_in_region(region_name='default'):
    '''Returns states of all instances in a given regions.'''

    if region_name == 'default':
        region_name = default_region_name()

    print('finging states of instances in', region_name)

    ec2 = boto3.resource('ec2', region_name)
    states = []
    print(region_name, 'collecting instances states')
    for instance in ec2.instances.all():
        states.append(instance.state['Name'])

    return states


def run_task_in_region(task='test', region_name='default', parallel=False, output=False):
    '''
    Runs a task from fabfile.py on all instances in a given region.
    :param string task: name of a task defined in fabfile.py
    :param string region_name: region from which instances are picked
    :param bool parallel: indicates whether task should be dispatched in parallel
    :param bool output: indicates whether output of task is needed
    '''

    if region_name == 'default':
        region_name = default_region_name()

    print('running task in', region_name)

    ip_list = instances_ip_in_region(region_name)
    if parallel:
        hosts = " ".join(["ubuntu@"+ip for ip in ip_list])
        cmd = 'parallel fab -i key_pairs/aleph.pem -H {} '+task+' ::: '+hosts
    else:
        hosts = ",".join(["ubuntu@"+ip for ip in ip_list])
        cmd = f'fab -i key_pairs/aleph.pem -H {hosts} {task}'

    try:
        if output:
            return check_output(cmd.split())
        return call(cmd.split())
    except Exception as e:
        print('paramiko troubles')


def run_cmd_in_region(cmd='ls', region_name='default', output=False):
    '''
    Runs a shell command cmd on all instances in a given region.
    :param string cmd: a shell command that is run on instances
    :param string region_name: region from which instances are picked
    :param bool output: indicates whether output of cmd is needed
    '''

    if region_name == 'default':
        region_name = default_region_name()


    print('running command in', region_name)

    ip_list = instances_ip_in_region(region_name)
    results = []
    for ip in ip_list:
        cmd_ = f'ssh -o "StrictHostKeyChecking no" -q -i key_pairs/aleph.pem ubuntu@{ip} -t "{cmd}"'
        if output:
            results.append(check_output(cmd_, shell=True))
        else:
            results.append(call(cmd_, shell=True))

    return results


def wait_in_region(target_state, region_name):
    '''Waits until all machines in a given region reach a given state.'''

    if region_name == 'default':
        region_name = default_region_name()

    print('waiting in', region_name)

    instances = all_instances_in_region(region_name)
    if target_state == 'running':
        for i in instances: i.wait_until_running()
    if target_state == 'terminated':
        for i in instances: i.wait_until_terminated()
    if target_state == 'ssh ready':
        ids = [instance.id for instance in instances]
        initializing = True
        while initializing:
            responses = boto3.client('ec2', region_name).describe_instance_status(InstanceIds=ids)
            statuses = responses['InstanceStatuses']
            all_initialized = True
            if statuses:
                for status in statuses:
                    if status['InstanceStatus']['Status'] != 'ok' or status['SystemStatus']['Status'] != 'ok':
                        all_initialized = False
            else:
                all_initialized = False

            if all_initialized:
                initializing = False
            else:
                print('.', end='')
                import sys
                sys.stdout.flush()
                sleep(5)
        print()


def installation_finished_in_region(region_name):
    '''Checks if installation has finished on all instances in a given region.'''

    ip_list = instances_ip_in_region(region_name)
    results = []
    cmd = "tail -1 setup.log"
    results = run_cmd_in_region(cmd, region_name, output=True)
    for result in results:
        if len(result) < 4 or result[:4] != b'done':
            return False

    print(f'installation in {region_name} finished')
    return True

#======================================================================================
#                              routines for all regions
#======================================================================================

def exec_for_regions(func, regions='badger regions', parallel=True):
    '''A helper function for running routines in all regions.'''

    if regions == 'all':
        regions = available_regions()
    if regions == 'badger regions':
        regions = badger_regions()

    results = []
    if parallel:
        try:
            results = Parallel(n_jobs=N_JOBS)(delayed(func)(region_name) for region_name in regions)
        except Exception as e:
            print('error during collecting results', type(e), e)
    else:
        for region_name in regions:
            results.append(func(region_name))

    if results and isinstance(results[0], list):
        return [res for res_list in results for res in res_list]

    return results


def launch_new_instances(nhpr, instance_type='t2.micro'):
    '''
    Launches n_hosts_per_region in ever region from given regions.
    :param dict nhpr: dict region_name --> n_hosts_per_region
    '''

    regions = nhpr.keys()

    failed = []
    print('launching instances')
    for region_name in regions:
        print(region_name, '', end='')
        instances = launch_new_instances_in_region(nhpr[region_name], region_name, instance_type)
        if not instances:
            failed.append(region_name)

    tries = 5
    while failed and tries:
        tries -= 1
        sleep(5)
        print('there were problems in launching instances in regions', *failed, 'retrying')
        for region_name in failed.copy():
            print(region_name, '', end='')
            instances = launch_new_instances_in_region(nhpr[region_name], region_name, instance_type)
            if instances:
                failed.remove(region_name)


def terminate_instances(regions='badger regions'):
    '''Terminates all instances in ever region from given regions.'''

    return exec_for_regions(terminate_instances_in_region, regions)


def all_instances(regions='badger regions'):
    '''Returns all running or pending instances from given regions.'''

    return exec_for_regions(all_instances_in_region, regions, parallel=False)


def instances_ip(regions='badger regions'):
    '''Returns ip addresses of all running or pending instances from given regions.'''

    return exec_for_regions(instances_ip_in_region, regions)


def instances_state(regions='badger regions'):
    '''Returns states of all instances in given regions.'''

    return exec_for_regions(instances_state_in_region, regions)


def run_task(task='test', regions='badger regions', parallel=False, output=False):
    '''
    Runs a task from fabfile.py on all instances in all given regions.
    :param string task: name of a task defined in fabfile.py
    :param list regions: collections of regions in which the tast should be performed
    :param bool parallel: indicates whether task should be dispatched in parallel
    :param bool output: indicates whether output of task is needed
    '''

    return exec_for_regions(partial(run_task_in_region, task, parallel=parallel, output=output), regions, parallel)


def run_cmd(cmd='ls', regions='badger regions', output=False, parallel=True):
    '''
    Runs a shell command cmd on all instances in all given regions.
    :param string cmd: a shell command that is run on instances
    :param list regions: collections of regions in which the tast should be performed
    :param bool parallel: indicates whether task should be dispatched in parallel
    :param bool output: indicates whether output of task is needed
    '''

    return exec_for_regions(partial(run_cmd_in_region, cmd, output=output), regions, parallel)


def wait(target_state, regions='badger regions'):
    '''Waits until all machines in all given regions reach a given state.'''

    exec_for_regions(partial(wait_in_region, target_state), regions)


def wait_install(regions='badger regions'):
    '''Waits till installation finishes in all given regions.'''

    sleep(60)
    wait_for_regions = regions.copy()
    while wait_for_regions:
        sleep(10)
        finished = []
        results = Parallel(n_jobs=N_JOBS)(delayed(installation_finished_in_region)(r) for r in wait_for_regions)

        wait_for_regions = [r for i,r in enumerate(wait_for_regions) if not results[i]]


#======================================================================================
#                               aggregates
#======================================================================================

def run_experiment(n_processes, regions, restricted, experiment, instance_type):
    '''Runs an experiment.'''

    start = time()
    parallel = n_processes > 1
    if regions == 'badger_regions':
        regions = badger_regions()
    if regions == 'all':
        regions = available_regions()

    # note: there are only 5 t2.micro machines in 'sa-east-1', 'ap-southeast-2' each
    print('launching machines')
    nhpr = n_hosts_per_regions(n_processes, regions, restricted)
    launch_new_instances(nhpr, instance_type)

    print('waiting for transition from pending to running')
    wait('running', regions)

    print('generating keys')
    # generate signing and keys
    generate_signing_keys(n_processes)

    print('generating hosts files')
    # prepare hosts file
    ip_list = instances_ip(regions)
    with open('hosts', 'w') as f:
        f.writelines([ip+'\n' for ip in ip_list])

    print('waiting till ports are open on machines')
    # this is really slow, and actually machines are ready earlier! refactor
    #wait('ssh ready', regions)
    sleep(60)

    # TODO try to prevent output of apt spoiling to console
    print('installing dependencies')
    # install dependencies on hosts
    run_task('inst-dep', regions, parallel)

    # TODO check if it works of more than 1 machine per region
    print('wait till installation finishes')
    # wait till installing finishes
    wait_install(regions)

    print('packing local repo')
    # pack testing repo
    call('fab -H 127.0.0.1 zip-repo'.split())

    print('sending testing repo')
    # send testing repo
    run_task('send-testing-repo', regions, parallel)

    print('syncing files')
    # send files: hosts, signing_keys, light_nodes_public_keys
    run_task('sync-files', regions, parallel)

    print(f'establishing the environment took {round(time()-start, 2)}s')
    # run the experiment
    run_task(experiment, regions, parallel)


def get_logs(regions=badger_regions()):
    '''Retrieves all logs from instances.'''

    run_task('get-logs', regions, parallel=True)

    print('read hosts')
    with open('hosts', 'r') as f:
        hosts_ip = [line[:-1] for line in f]

    print('read signing keys')
    with open('signing_keys', 'r') as f:
        hexes = [line[:-1].encode() for line in f]
        signing_keys = [SigningKey(hexed) for hexed in hexes]

    pk_hexes = [VerifyKey.from_SigningKey(sk).to_hex() for sk in signing_keys]
    arg_sort = [i for i, _ in sorted(enumerate(pk_hexes), key = lambda x: x[1])]

    signing_keys = [signing_keys[i] for i in arg_sort]
    hosts_ip = [hosts_ip[i] for i in arg_sort]

    print('write hosts')
    with open('hosts_sorted', 'w') as f:
        for ip in hosts_ip:
            f.write(ip+'\n')

    print('write signing keys')
    with open('signing_keys_sorted', 'w') as f:
        for sk in signing_keys:
            f.write(sk.to_hex().decode()+'\n')

    print('rename results')
    for fp in os.listdir('../results'):
        pid = hosts_ip.index(fp.split('-aleph.log')[0].replace('-','.'))
        os.rename(f'../results/{fp}', f'../results/{pid}.aleph.log')


def memory_usage(regions=badger_regions()):
    cmd = 'grep memory proof-of-concept/experiments/aleph.log | tail -1'
    output = run_cmd(cmd, regions, True)
    results = [float(line.split()[7]) for line in output]
    return min(results), np.mean(results), max(results)


def reached_max_level(regions):
    cmd = 'grep max_level proof-of-concept/experiments/aleph.log'
    output = run_cmd(cmd, regions, True)


#======================================================================================
#                                        shortcuts
#======================================================================================

tr = run_task_in_region
t = run_task

cmr = run_cmd_in_region
cm = run_cmd

e = run_experiment

ti = terminate_instances

A = [104, badger_regions(), [], 'simple-ec2-test', 't2.medium']
res = ['sa-east-1', 'ap-southeast-2']

rs = lambda n=8: e(n, badger_regions(), res, 'simple-ec2-test', 't2.micro')
ms = lambda regions=badger_regions(): memory_usage(regions)

#======================================================================================
#                                         main
#======================================================================================

if __name__=='__main__':
    assert os.getcwd().split('/')[-1] == 'aws', 'Wrong dir! go to experiments/aws'

    from IPython import embed
    from traitlets.config import get_config
    c = get_config()
    c.InteractiveShellEmbed.colors = "Linux"
    embed(config=c)
