'''This module implements unit - a basic building block of Aleph protocol.'''


class Unit(object):
    '''This class is the building block for the poset'''

    __slots__ = ['creator_id', 'parents', 'txs', 'signature', 'coinshares', 'level']

    def __init__(self, creator_id, parents, txs, signature=None, coinshares=None, level=None):
        '''
        :param int creator_id: indentification number of a process creating this unit
        :param list parents: list of hashes of parent units; first parent has to be above a unit created by the process creator_id
        :param list txs: list of transactions
        :param int signature: signature made by a process creating this unit preventing forging units by Byzantine processes
        :param list coinshares: list of coinshares if this is a prime unit, null otherwise
        '''
        self.creator_id = creator_id
        self.parents = parents
        self.txs = txs
        self.signature = signature
        self.coinshares = coinshares
        self.level = level

    def hash(self):
        '''
        Hashing function used to hide addressing differences among the committee
        '''
        pass

