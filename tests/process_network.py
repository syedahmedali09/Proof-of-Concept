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

#!/usr/bin/env python3
import asyncio
import multiprocessing
import pickle
import random
import subprocess

from aleph.network import tx_generator
from aleph.data_structures import Poset, UserDB
from aleph.process import Process
from aleph.crypto.keys import SigningKey, VerifyKey

DISCOVERY_PORT = 49643

TRANSACTIONS_PER_SECOND = 30

def get_priv_keys(keyfile):
    result = []
    with open(keyfile, "r") as the_file:
        for hexed in the_file.readlines():
            result.append(SigningKey(hexed[:-1].encode('utf8')))
    return result

def get_pub_keys(keyfile):
    result = []
    with open(keyfile, "r") as the_file:
        for hexed in the_file.readlines():
            result.append(hexed[:-1].encode('utf8'))
    return result

def make_discovery_response(priv_keys):
    result = {}
    process_port = DISCOVERY_PORT
    for priv_key in priv_keys:
        process_port += 1
        result[process_port] = VerifyKey.from_SigningKey(priv_key).to_hex()
    return result

def make_database_response(account_priv_keys):
    account_public_keys = [VerifyKey.from_SigningKey(pk) for pk in account_priv_keys]
    return [(pubk.to_hex(), random.randrange(10000, 100000), -1) for pubk in account_public_keys]

def put_message(writer, message):
    writer.write(str(len(message)).encode())
    writer.write(b'\n')
    writer.write(message)

def make_discovery_server(priv_keys, account_priv_keys):
    response = []
    if account_priv_keys is not None:
        response.append(pickle.dumps('tx'))
        response.append(pickle.dumps(make_database_response(account_priv_keys)))
    response.append(pickle.dumps(make_discovery_response(priv_keys)))
    async def discovery_server(reader, writer):
        for resp in response:
            put_message(writer, resp)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    return discovery_server

def get_ip_candidates(ip_range):
    ips = subprocess.Popen(
            "nmap -oG - -p"+str(DISCOVERY_PORT)+" "+ip_range+" | awk '/49643\/open/{print $2}'",
            shell=True,
            stdout=subprocess.PIPE).stdout.read().split(b'\n')[:-1]
    return set(ips)

async def get_message(reader):
    data = await reader.readuntil()
    n_bytes = int(data[:-1])
    data = await reader.readexactly(n_bytes)
    return pickle.loads(data)

async def discover_at(ip, all_pub_keys):
    print("Discovering at "+ ip)
    reader, writer = await asyncio.open_connection(ip, DISCOVERY_PORT)
    message = await get_message(reader)
    database = None
    if message == 'tx':
        database = await get_message(reader)
        message = await get_message(reader)
    keys_by_port = message
    result = {}
    for port, key in keys_by_port.items():
        if key in all_pub_keys:
            result[key] = (ip, port)
    return result, database

async def discover(all_pub_keys, ip_range):
    client_map = {}
    database = None
    checked_ips = set()
    while len(client_map) < len(all_pub_keys):
        await asyncio.sleep(1)
        ip_candidates = get_ip_candidates(ip_range) - checked_ips
        discovery_tasks = [asyncio.create_task(discover_at(ip.decode('utf8'), all_pub_keys)) for ip in ip_candidates]
        new_clients = await asyncio.gather(*discovery_tasks)
        for client in new_clients:
            client_map.update(client[0])
            if client[1] is not None:
                database = client[1]
        checked_ips.update(ip_candidates)
    assert(database is not None)
    return client_map, database

def process_client_map(client_map):
    addresses, public_keys = [], []
    for pub_key in sorted(client_map):
        public_keys.append(pub_key)
        addresses.append(client_map[pub_key])
    return addresses, public_keys

async def run_processes(client_map, priv_keys, database, account_priv_keys):
    addresses, public_key_hexes = process_client_map(client_map)
    public_keys = [VerifyKey.from_hex(pub_key) for pub_key in public_key_hexes]
    n_processes = len(public_keys)
    tasks = []
    for priv_key in priv_keys:
        pub_key = VerifyKey.from_SigningKey(priv_key)
        process_id = public_key_hexes.index(pub_key.to_hex())
        tx_receiver_address = (addresses[process_id][0], addresses[process_id][1]+32)
        new_process = Process(n_processes, process_id, priv_key, pub_key, addresses, public_keys, tx_receiver_address, UserDB(database))
        tasks.append(asyncio.create_task(new_process.run()))
    if account_priv_keys is not None:
        tx_rec_addresses = [(adr[0], adr[1]+32) for adr in addresses]
        await asyncio.sleep(1)
        p = multiprocessing.Process(target=tx_generator, args=(tx_rec_addresses, account_priv_keys, TRANSACTIONS_PER_SECOND))
        p.start()
        await asyncio.gather(*tasks)
        p.kill()
    else:
        await asyncio.gather(*tasks)

async def run():
    # arguments: private keys, public keys, our IP, IP range, whether to produce transactions (0 or 1)
    import sys
    assert(len(sys.argv) == 6)
    priv_keys_file = sys.argv[1]
    pub_keys_file = sys.argv[2]
    our_ip = sys.argv[3]
    ip_range = sys.argv[4]
    generate_txs = int(sys.argv[5]) == 1

    priv_keys = get_priv_keys(priv_keys_file)
    all_pub_keys = get_pub_keys(pub_keys_file)

    account_priv_keys = None
    if generate_txs:
        account_priv_keys = [SigningKey() for _ in range(100)]

    discovery_server = make_discovery_server(priv_keys, account_priv_keys)
    async def serve():
        server = await asyncio.start_server(discovery_server, our_ip, DISCOVERY_PORT)
        async with server:
            await server.serve_forever()
    server_task = asyncio.create_task(serve())

    client_map, database = await discover(all_pub_keys, ip_range)

    await run_processes(client_map, priv_keys, database, account_priv_keys)

if __name__ == '__main__':
    asyncio.run(run())
