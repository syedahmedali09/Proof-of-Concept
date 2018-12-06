import asyncio
import marshal
import logging
import time

from aleph.data_structures import Unit
from aleph.config import *

async def listener(poset, process_id, addresses, executor):
    n_recv_syncs = 0

    async def listen_handler(reader, writer):
        nonlocal n_recv_syncs
        logger = logging.getLogger(LOGGING_FILENAME)

        ips = [ip for ip, _ in addresses]
        peer_addr = writer.get_extra_info('peername')
        #logger.debug('listener: assuming that addresses are different')

        if peer_addr[0] not in ips:
            logger.info(f'Closing connection with {peer_addr[0]}, it is not in address book')
            return

        if n_recv_syncs > N_RECV_SYNC:
            logger.info(f'Too many synchronizations, rejecting {peer_addr}')
            return

        n_recv_syncs += 1
        logger.info(f'listener {process_id}: connection established with an unknown process')

        logger.info(f'listener {process_id}: receiving info about forkers and heights&hashes from an unknown process')
        data = await reader.readuntil()
        n_bytes = int(data[:-1])
        data = await reader.read(n_bytes)
        ex_id, ex_heights, ex_hashes = marshal.loads(data)
        assert ex_id != process_id, "It seems we are syncing with ourselves."
        assert ex_id in range(poset.n_processes), "Incorrect process id received."
        logger.info(f'listener {process_id}: got forkers/heights {ex_heights} from {ex_id}')

        int_heights, int_hashes = poset.get_max_heights_hashes()

        logger.info(f'listener {process_id}: sending info about forkers and heights&hashes to {ex_id}')

        data = marshal.dumps((process_id, int_heights, int_hashes))
        writer.write(str(len(data)).encode())
        writer.write(b'\n')
        writer.write(data)
        await writer.drain()
        logger.info(f'listener {process_id}: sending forkers/heights {int_heights} to {ex_id}')

        # receive units
        logger.info(f'listener {process_id}: receiving units from {ex_id}')
        data = await reader.readuntil()
        n_bytes = int(data[:-1])
        data = await reader.read(n_bytes)
        units_received = marshal.loads(data)
        logger.info(f'listener {process_id}: received units')

        '''
        # verifye signatures
        logger.info(f'listener {process_id}: verifying signatures')
        loop = asyncio.get_running_loop()
        # TODO check if it possible to create one tast that waits for verifying all units
        # TODO check if done, pending = asyncio.wait(tasks, return_when=FIRST_COMPLETED) can be used for breaking as soon as some signature is broken.
        tasks = [loop.run_in_executor(executor, verify_signature, unit) for unit in units_received]
        results = await asyncio.gather(*tasks)
        if not all(results):
            logger.info(f'listener {process_id}: got a unit from {ex_id} with invalid signature; aborting')
            n_recv_syncs -= 1
            return
        logger.info(f'listener {process_id}: signatures verified')
        '''


        logger.info(f'listener {process_id}: trying to add {len(units_received)} units from {ex_id} to poset')
        for unit in units_received:
            assert all(U_hash in poset.units.keys() for U_hash in unit['parents_hashes'])
            parents = [poset.unit_by_hash(parent_hash) for parent_hash in unit['parents_hashes']]
            U = Unit(unit['creator_id'], parents, unit['txs'], unit['signature'], unit['coinshares'])
            if U.hash() not in poset.units.keys():
                if poset.check_compliance(U):
                    poset.add_unit(U)
                else:
                    logger.error(f'listener {process_id}: got unit from {ex_id} that does not comply to the rules; aborting')
                    n_recv_syncs -= 1
                    return
        logger.info(f'listener {process_id}: units from {ex_id} were added succesfully')

        send_ind = [i for i, (int_height, ex_height) in enumerate(zip(int_heights, ex_heights)) if int_height > ex_height]

        # send units
        logger.info(f'listener {process_id}: sending units to {ex_id}')
        units_to_send = []
        for i in send_ind:
            units = poset.units_by_height_interval(creator_id=i, min_height=ex_heights[i]+1, max_height=int_heights[i])
            units_to_send.extend(units)
        units_to_send = poset.order_units_topologically(units_to_send)
        units_to_send = [unit_to_dict(U) for U in units_to_send]
        data = marshal.dumps(units_to_send)
        writer.write(str(len(data)).encode())
        writer.write(b'\n')
        writer.write(data)
        await writer.drain()
        logger.info(f'listener {process_id}: units sent to {ex_id}')

        logger.info(f'listener {process_id}: syncing with {ex_id} completed succesfully')
        n_recv_syncs -= 1
        writer.close()
        await writer.wait_closed()


    host_addr = addresses[process_id]
    server = await asyncio.start_server(listen_handler, host_addr[0], host_addr[1])

    logger = logging.getLogger(LOGGING_FILENAME)
    logger.info(f'Serving on {host_addr}')

    async with server:
        await server.serve_forever()



async def sync(poset, initiator_id, target_id, target_addr, executor):
    logger = logging.getLogger(LOGGING_FILENAME)

    logger.info(f'sync {initiator_id} -> {target_id}: establishing connection to {target_id}')
    reader, writer = await asyncio.open_connection(target_addr[0], target_addr[1])
    logger.info(f'sync {initiator_id} -> {target_id}: established connection to {target_id}')

    int_heights, int_hashes = poset.get_max_heights_hashes()

    logger.info(f'sync {initiator_id} -> {target_id}: sending info about own process_id and forkers/heights/hashes to {target_id}')
    #print(int_heights, int_hashes)
    data = marshal.dumps((initiator_id, int_heights, int_hashes))
    writer.write(str(len(data)).encode())
    writer.write(b'\n')
    writer.write(data)
    await writer.drain()
    logger.info(f'sync {initiator_id} -> {target_id}: sent own process_id forkers/heights/hashes {int_heights} to {target_id}')


    logger.info(f'sync {initiator_id} -> {target_id}: receiving info about target identity and forkers/heights/hashes from {target_id}')
    data = await reader.readuntil()
    n_bytes = int(data[:-1])
    data = await reader.read(n_bytes)
    ex_id, ex_heights, ex_hashes = marshal.loads(data)
    assert ex_id == target_id, "The process_id sent by target does not much the intented target_id"
    logger.info(f'sync {initiator_id} -> {target_id}: got target identity and forkers/heights/hashes {ex_heights} from {target_id}')

    # send units
    send_ind = [i for i, (int_height, ex_height) in enumerate(zip(int_heights, ex_heights)) if int_height > ex_height]
    logger.info(f'sync {initiator_id} -> {target_id}: sending units to {target_id}')
    units_to_send = []
    for i in send_ind:
        units = poset.units_by_height_interval(creator_id=i, min_height=ex_heights[i]+1, max_height=int_heights[i])
        units_to_send.extend(units)
    units_to_send = poset.order_units_topologically(units_to_send)
    units_to_send = [unit_to_dict(U) for U in units_to_send]
    data = marshal.dumps(units_to_send)
    writer.write(str(len(data)).encode())
    writer.write(b'\n')
    writer.write(data)
    await writer.drain()
    logger.info(f'sync {initiator_id} -> {target_id}: units sent to {target_id}')

    # receive units
    logger.info(f'sync {initiator_id} -> {target_id}: receiving units from {target_id}')
    data = await reader.readuntil()
    n_bytes = int(data[:-1])
    data = await reader.read(n_bytes)
    units_received = marshal.loads(data)
    logger.info(f'sync {initiator_id} -> {target_id}: received units')

    '''
    # verify signatures
    logger.info(f'sync {initiator_id}: verifying signatures')
    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(executor, verify_signature, unit) for unit in units_received]
    results = await asyncio.gather(*tasks)
    if not all(results):
        logger.info(f'sync {initiator_id}: got a unit from {ex_id} with invalid signature; aborting')
        return
    logger.info(f'sync {initiator_id}: signatures verified')
    '''


    logger.info(f'sync {initiator_id} -> {target_id}: trying to add {len(units_received)} units from {target_id} to poset')
    for unit in units_received:
        assert all(U_hash in poset.units.keys() for U_hash in unit['parents_hashes'])
        parents = [poset.unit_by_hash(parent_hash) for parent_hash in unit['parents_hashes']]
        U = Unit(unit['creator_id'], parents, unit['txs'], unit['signature'], unit['coinshares'])
        if U.hash() not in poset.units.keys():
                if poset.check_compliance(U):
                    poset.add_unit(U)
                else:
                    logger.error(f'listener {process_id}: got unit from {ex_id} that does not comply to the rules; aborting')
                    n_recv_syncs -= 1
                    return
    logger.info(f'sync {initiator_id} -> {target_id}: units from {target_id} added succesfully')


    logger.info(f'sync {initiator_id} -> {target_id}: syncing with {target_id} completed succesfully')

    # TODO: at some point we need to add exceptions and exception handling and make sure that the two lines below are executed no matter what happens
    writer.close()
    await writer.wait_closed()


def verify_signature(unit):
    '''Verifies signatures of the unit and all txs in it'''
    # TODO this is a prosthesis
    time.sleep(.1)
    return True


def unit_to_dict(U):
    parents_hashes = [parent.hash() for parent in U.parents]
    return {'creator_id': U.creator_id,
            'parents_hashes': parents_hashes,
            'txs': U.txs,
            'signature': U.signature,
            'coinshares': U.coinshares}
