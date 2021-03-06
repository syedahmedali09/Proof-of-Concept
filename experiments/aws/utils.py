'''
    This is a Proof-of-Concept implementation of Aleph Zero consensus protocol.
    Copyright (C) 2019 Aleph Zero Team
    
    This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    
    You should have received a copy of the GNU General Public License
    along with this program. If not, see <http://www.gnu.org/licenses/>.
'''

'''Helper functions for shell'''

import os
from pathlib import Path
from subprocess import call

import boto3

from aleph.crypto.keys import SigningKey


def image_id_in_region(region_name, version='bionic'):
    '''Find id of os image we use. The id may differ for different regions'''

    if version == 'bionic':
    	image_name = 'ubuntu/images/hvm-ssd/ubuntu-bionic-18.04-amd64-server-20190210'
    elif version == 'cosmic':
        image_name = 'ubuntu/images/hvm-ssd/ubuntu-cosmic-18.10-amd64-server-20190110'

    ec2 = boto3.resource('ec2', region_name)
    # in the below, there is only one image in the iterator
    for image in ec2.images.filter(Filters=[{'Name': 'name', 'Values':[image_name]}]):
        return image.id


def vpc_id_in_region(region_name):
    '''Find id of vpc in a given region. The id may differ for different regions'''

    ec2 = boto3.resource('ec2', region_name)
    vpcs_ids = []
    for vpc in ec2.vpcs.all():
        vpcs_ids.append(vpc.id)

    if len(vpcs_ids) > 1 or not vpcs_ids:
        raise Exception(f'Found {len(vpcs_ids)} vpc, expected one!')

    return vpcs_ids[0]


def create_security_group(region_name, security_group_name):
    '''Creates security group that allows connecting via ssh and ports needed for sync'''

    ec2 = boto3.resource('ec2', region_name)

    # get the id of vpc in the given region
    vpc_id = vpc_id_in_region(region_name)
    sg = ec2.create_security_group(GroupName=security_group_name, Description='ssh and gossip', VpcId=vpc_id)

    # authorize incomming connections to port 22 for ssh, mainly for debugging
    # and to port 8888 for syncing the posets
    sg.authorize_ingress(
        GroupName=security_group_name,
        IpPermissions=[
            {
                'FromPort': 22,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 22,
            },
            {
                'FromPort': 8888,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 8888,
            }
        ]
    )
    # authorize outgoing connections from ports 8000-20000 for intiating syncs
    sg.authorize_egress(
        IpPermissions=[
            {
                'FromPort': 8000,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 20000,
            }
        ]
    )

    return sg.id


def security_group_id_by_region(region_name, security_group_name):
    '''Finds id of a security group. It may differ for different regions'''

    ec2 = boto3.resource('ec2', region_name)
    security_groups = ec2.security_groups.all()
    for security_group in security_groups:
        if security_group.group_name == security_group_name:
            return security_group.id

    # it seems that the group does not exist, let fix that
    return create_security_group(region_name, security_group_name)


def check_key_uploaded_all_regions(key_name='aleph'):
    '''Checks if in all regions there is public key corresponding to local private key.'''

    key_path = f'key_pairs/{key_name}.pem'
    assert os.path.exists(key_path), 'there is no key locally!'
    fingerprint_path = f'key_pairs/{key_name}.fingerprint'
    assert os.path.exists(fingerprint_path), 'there is no fingerprint of the key!'

    # read the fingerprint of the key
    with open(fingerprint_path, 'r') as f:
        fp = f.readline()

    for region_name in available_regions():
        ec2 = boto3.resource('ec2', region_name)
        # check if there is any key which fingerprint matches fp
        if not any(key.key_fingerprint == fp for key in ec2.key_pairs.all()):
            return False

    return True


def generate_key_pair_all_regions(key_name='aleph'):
    '''Generates key pair, stores private key locally, and sends public key to all regions'''

    key_path = f'key_pairs/{key_name}.pem'
    fingerprint_path = f'key_pairs/{key_name}.fingerprint'
    assert not os.path.exists(key_path), 'key exists, just use it!'

    print('        generating key pair')
    # generate a private key
    call(f'openssl genrsa -out {key_path} 2048'.split())
    # give the private key appropriate permissions
    call(f'chmod 400 {key_path}'.split())
    # generate a public key corresponding to the private key
    call(f'openssl rsa -in {key_path} -outform PEM -pubout -out {key_path}.pub'.split())
    # read the public key in a form needed by aws
    with open(key_path+'.pub', 'r') as f:
        pk_material = ''.join([line[:-1] for line in f.readlines()[1:-1]])

    # we need fingerpring of the public key in a form generated by aws, hence
    # we need to send it there at least once
    wrote_fp = False
    for region_name in available_regions():
        ec2 = boto3.resource('ec2', region_name)
        # first delete the old key
        for key in ec2.key_pairs.all():
            if key.name == key_name:
                print(f'        deleting old key {key.name} in region', region_name)
                key.delete()
                break

        # send the public key to current region
        print('        sending key pair to region', region_name)
        ec2.import_key_pair(KeyName=key_name, PublicKeyMaterial=pk_material)

        # write fingerprint
        if not wrote_fp:
            with open(fingerprint_path, 'w') as f:
                f.write(ec2.KeyPair(key_name).key_fingerprint)
            wrote_fp = True


def init_key_pair(region_name, key_name='aleph', dry_run=False):
    ''' Initializes key pair needed for using instances.'''

    key_path = f'key_pairs/{key_name}.pem'
    fingerprint_path = f'key_pairs/{key_name}.fingerprint'

    if os.path.exists(key_path) and os.path.exists(fingerprint_path):
        # we have the private key locally so let check if we have pk in the region

        if not dry_run:
            print('        found local key; ', end='')
        ec2 = boto3.resource('ec2', region_name)
        with open(fingerprint_path, 'r') as f:
            fp = f.readline()

        keys = ec2.key_pairs.all()
        for key in keys:
            if key.name == key_name:
                if key.key_fingerprint != fp:
                    if not dry_run:
                        print('there is old version of key in region', region_name)
                    # there is an old version of the key, let remove it
                    key.delete()
                else:
                    if not dry_run:
                        print('local and upstream key match')
                    # check permissions
                    call(f'chmod 400 {key_path}'.split())
                    # everything is alright

                    return

        # for some reason there is no key up there, let send it
        with open(key_path+'.pub', 'r') as f:
            pk_material = ''.join([line[:-1] for line in f.readlines()[1:-1]])
        ec2.import_key_pair(KeyName=key_name, PublicKeyMaterial=pk_material)
    else:
        # we don't have the private key, let create it
        generate_key_pair_all_regions(key_name)


def read_aws_keys():
    ''' Reads access and secret access keys needed for connecting to aws.'''

    creds_path = str(Path.joinpath(Path.home(), Path('.aws/credentials')))
    with open(creds_path, 'r') as f:
        f.readline() # skip block description
        access_key_id = f.readline().strip().split('=')[-1].strip()
        secret_access_key = f.readline().strip().split('=')[-1].strip()

        return access_key_id, secret_access_key


def generate_keys(n_processes):
    ''' Generate signing keys for the committee.'''

    # if file exists check if it is of appropriate size
    if os.path.exists('signing_keys'):
        with open('signing_keys', 'r') as f:
            if n_processes == sum(1 for line in f):
                return

    priv_keys = [SigningKey() for _ in range(n_processes)]
    with open('signing_keys', 'w') as f:
        for _ in range(n_processes):
            f.write(SigningKey().to_hex().decode()+'\n')


def all_regions():
    return available_regions() + ['eu-west-2']

def available_regions():
    ''' Returns a list of all currently available regions.'''
    non_badger_regions = list(set(boto3.Session().get_available_regions('ec2'))-set(badger_regions()))
    regions = badger_regions()+non_badger_regions
    for rn in ['ap-northeast-2', 'eu-west-3', 'eu-west-2', 'eu-north-1']:
        regions.remove(rn)

    return regions


def eu_regions():
    eu_regs = []
    for region in available_regions():
        if region.startswith('eu'):
            eu_regs.append(region)

    return eu_regs


def badger_regions():
    ''' Returns regions used by hbbft in theri experiments'''

    return ['us-east-1', 'us-west-1', 'us-west-2', 'eu-west-1',
            'sa-east-1', 'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1']


def default_region_name():
    ''' Helper function for getting default region name for current setup.'''

    return boto3.Session().region_name


def describe_instances(region_name):
    ''' Prints launch indexes and state of all instances in a given region.'''

    ec2 = boto3.resource('ec2', region_name)
    for instance in ec2.instances.all():
        print(f'ami_launch_index={instance.ami_launch_index} state={instance.state}')


def n_processes_per_regions(n_processes, regions=badger_regions(), restricted={'sa-east-1':5, 'ap-southeast-2':5}):
    bound_n_processes = 64*(len(regions)-len(restricted))
    for r in restricted:
        bound_n_processes += restricted[r]
    assert n_processes <= bound_n_processes, 'n_processes exceeds instances available on AWS'

    nhpr = {}
    n_left = n_processes
    unrestricted = [r for r in regions if r not in restricted.keys()]
    if restricted and n_processes/len(regions) > min(restricted.values()):
        nh = n_processes
        for r in restricted:
            nh -= restricted[r]
        nh //= (len(unrestricted))
        for ur in unrestricted:
            nhpr[ur] = nh
            n_left -= nh
        for r in restricted:
            if restricted[r]:
                nhpr[r] = restricted[r]
                n_left -= restricted[r]

        for i in range(n_left):
            nhpr[unrestricted[i]] += 1

    else:
        for r in regions:
            nhpr[r] = n_processes // len(regions)
            n_left -= n_processes // len(regions)

        for i in range(n_left):
            nhpr[regions[i]] += 1

    for r in regions:
        if r in nhpr and not nhpr[r]:
            nhpr.pop(r)

    return nhpr

def color_print(string):
    print('\x1b[6;30;42m' + string + '\x1b[0m')
