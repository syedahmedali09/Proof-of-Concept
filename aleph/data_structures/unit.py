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

'''This module implements unit - a basic building block of Aleph protocol.'''
from aleph.crypto import sha3_hash
import pickle
import zlib
import base64

from aleph.config import PAIRING_GROUP

class Unit(object):
    '''
    This class is the building block for the poset

    :param int creator_id: indentification number of a process creating this unit
    :param list parents: list of parent units; first parent has to be the last unit created by the process creator_id
    :param list txs: list of transactions
    :param bytes signature: signature made by a process creating this unit preventing forging units by Byzantine processes
    :param list coin_shares: list of coin_shares if this is a prime unit, None otherwise
    '''

    __slots__ = ['creator_id', 'parents', 'txs', 'signature', '_coin_shares',
                 'level', 'floor', 'height', 'hash_value', 'n_txs']

    def __init__(self, creator_id, parents, txs, signature=None, coin_shares=None):
        self.creator_id = creator_id
        self.parents = parents
        self.signature = signature
        self._coin_shares = coin_shares or []
        self.level = None
        self.hash_value = None
        self.txs = zlib.compress(pickle.dumps(txs), level=4)
        self.n_txs = len(txs)
        self.height = parents[0].height+1 if len(parents) > 0 else 0


    @property
    def self_predecessor(self):
        return self.parents[0] if len(self.parents) > 0 else None


    @property
    def coin_shares(self):
        return self._coin_shares


    @coin_shares.setter
    def coin_shares(self, value):
        self._coin_shares = value
        self.hash_value = None


    def transactions(self):
        '''Returns the list of transactions contained in the unit.'''
        return list(pickle.loads(zlib.decompress(self.txs)))


    def parents_hashes(self):
        return [V.hash() for V in self.parents] if (self.parents and isinstance(self.parents[0], Unit)) else self.parents


    def bytestring(self):
        '''Create a bytestring with all essential info about this unit for the purpose of signature creation and checking.'''
        creator = str(self.creator_id).encode()
        serialized_shares = _serialize_and_flatten_coin_shares(self.coin_shares)
        return b'|'.join([creator] + self.parents_hashes() + serialized_shares + [self.txs])


    def short_name(self):
        '''
        Returns a 12 character string (surrounded by '< >' brackets) -- a shorter hash of the unit. To be used for printing units in logs.
        NOTE: this has collision resistance as long there are roughly <= 10^9 units considered simultaneusly.
        NOTE: this uses only characters in the set A-Z, 2-7 (base32 encoding)
        '''
        return pretty_hash(self.hash())


    def __getstate__(self):
        serialized_coin_shares = _serialize_coin_shares(self.coin_shares)
        return (self.creator_id, self.parents_hashes(), self.txs, self.n_txs, self.signature, serialized_coin_shares)


    def __setstate__(self, state):
        self.creator_id, self.parents, self.txs, self.n_txs, self.signature, serialized_coin_shares = state
        self.coin_shares = _deserialize_coin_shares(serialized_coin_shares)
        self.level = None
        self.hash_value = None


    def hash(self):
        '''Returns the value of hash of this unit.'''
        if self.hash_value is not None:
            return self.hash_value
        self.hash_value = sha3_hash(self.bytestring())
        return self.hash_value


    def __hash__(self):
        return hash(self.hash())


    def __eq__(self, other):
        return isinstance(other, Unit) and self.hash() == other.hash()


    def __str__(self):
        # create a string containing all the essential data in the unit
        str_repr =  str(self.creator_id)
        str_repr += str(self.parents_hashes())
        str_repr += str(self.txs)
        str_repr += str(self.coin_shares)
        return str_repr

    __repr__ = __str__


def pretty_hash(some_hash):
    '''
    Returns a 12 character string (surrounded by '< >' brackets) -- a shorter hash. To be used for printing hashes in logs.
    NOTE: this has collision resistance as long there are roughly <= 10^9 units considered simultaneusly.
    NOTE: this uses only characters in the set A-Z, 2-7 (base32 encoding)
    '''
    base32_hash = base64.b32encode(some_hash[:8]).decode()
    return '<'+base32_hash[:12]+'>'


def _serialize_coin_shares(coin_shares):
    if isinstance(coin_shares, dict):
        # These coin shares come from a dealing units -- represent threshold coins
        serialized_shares = {}
        serialized_shares['sks'] = [PAIRING_GROUP.serialize(sk, compression = False) for sk in coin_shares['sks']]
        serialized_shares['vks'] = [PAIRING_GROUP.serialize(vk, compression = False) for vk in coin_shares['vks']]
        serialized_shares['vk'] = PAIRING_GROUP.serialize(coin_shares['vk'], compression = False)
        return serialized_shares
    else:
        # These coin shares come from a non-dealing unit -- they just represent regular coin shares
        return [PAIRING_GROUP.serialize(cs, compression = False) for cs in coin_shares]


def _deserialize_coin_shares(serialized_shares):
    if isinstance(serialized_shares, dict):
        # These coin shares come from a dealing units -- represent threshold coins
        coin_shares = {}
        coin_shares['sks'] = [PAIRING_GROUP.deserialize(sk, compression = False) for sk in serialized_shares['sks']]
        coin_shares['vks'] = [PAIRING_GROUP.deserialize(vk, compression = False) for vk in serialized_shares['vks']]
        coin_shares['vk'] = PAIRING_GROUP.deserialize(serialized_shares['vk'], compression = False)
        return coin_shares
    else:
        # These coin shares come from a non-dealing unit -- they just represent regular coin shares
        return [PAIRING_GROUP.deserialize(cs, compression = False) for cs in serialized_shares]


def _serialize_and_flatten_coin_shares(coin_shares):
    '''Return a list of bytestrings as a representation of coin shares.'''
    if isinstance(coin_shares,dict):
        # we need to transform a dict of bytestrings into a list of bytestrings
        serialized_shares = _serialize_coin_shares(coin_shares)
        return serialized_shares['sks'] + serialized_shares['vks'] + [serialized_shares['vk']]
    else:
        # already in the right format
        return _serialize_coin_shares(coin_shares)
