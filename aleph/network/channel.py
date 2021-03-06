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

import asyncio
import logging

import aleph.const as consts


class RejectException(Exception):
    pass


class Channel:
    ''' Simple class representing an asynchronous communication channel through the network. Suitable for both a case when I am initiating connection (see open()) or when someone else does that (see connect()).

        Class representing an asynchronous communication channel through the network. Suitable for both a case when we are
        initiating a connection (see open()) or when someone else does that (see connect()).
        :param int owner_id: process ID of the owner of the channel
        :param int peer_id: process ID of the recipient (other end) of the channel
        :param tuple peer_address: pair (IP, port) with peer's address

    '''

    REJECT = b'REJECT'

    def __init__(self, owner_id, peer_id, peer_address):
        self.owner_id = owner_id
        self.peer_id = peer_id
        self.address = peer_address
        self.active = asyncio.Event()
        self.in_use = asyncio.Lock()
        self.reader = None
        self.writer = None

    @staticmethod
    async def receive_handshake(reader, writer):
        '''Receive handshake from an unknown process and find out their process_id.'''

        data = await reader.readuntil()
        return int(data.rstrip(b'\n'))

    def send_handshake(self):
        '''Introduce yourself (send process_id) to newly connected process.'''

        self.writer.write(f'{self.owner_id}\n'.encode())

    def connect(self, reader, writer):
        '''Activate channel by connecting existing reader and writer to it.'''

        self.reader = reader
        self.writer = writer
        self.active.set()

    def is_active(self):
        '''Guess what...'''

        return self.active.is_set()

    async def reject(self):
        '''Send REJECT message.'''

        if self.is_active():
            self.writer.write(self.REJECT)
            self.writer.write(b'\n')
            await self.writer.drain()

    async def read(self):
        '''
        Read data from the channel.
        If channel has not been activated yet, block and wait.
        If obtained REJECT message, raise RejectException.
        '''

        await self.active.wait()

        data = await self.reader.readuntil()
        data = data.rstrip(b'\n')
        if data == self.REJECT:
            raise RejectException()
        n_bytes = int(data)
        data = await self.reader.readexactly(n_bytes)
        return data

    async def write(self, data):
        '''Send data through the channel.'''

        if not self.is_active():
            await self.open()

        self.writer.write(str(len(data)).encode())
        self.writer.write(b'\n')
        self.writer.write(data)
        await self.writer.drain()

    async def open(self):
        '''Activate the channel by opening a new connection to the peer.'''

        logger = logging.getLogger(consts.LOGGER_NAME)
        logger.info(f'sync_open_chan {self.owner_id} | Opening connection to {self.peer_id} - start')
        while True:
            fut = asyncio.open_connection(*self.address)
            try:
                self.reader, self.writer = await asyncio.wait_for(fut, timeout=1)
                break
            except (asyncio.TimeoutError, ConnectionRefusedError):
                logger.info(f'sync_open_chan {self.owner_id} | Opening connection to {self.peer_id} - failed')
                await asyncio.sleep(1)

        logger.info(f'sync_open_chan {self.owner_id} | Opening connection to {self.peer_id} - succeded')

        self.send_handshake()
        self.active.set()

    async def close(self):
        '''Close the channel (unused for now).'''

        if self.is_active():
            self.writer.close()
            await self.writer.wait_closed()
            self.reader, self.writer = None, None
            self.active.clear()
