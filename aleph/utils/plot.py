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

import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore",category=DeprecationWarning)
    import networkx as nx
    from networkx.drawing.nx_agraph import graphviz_layout

import numpy as np
import logging
logging.getLogger('matplotlib').setLevel(logging.WARNING)
import matplotlib.pyplot as plt

from aleph.utils.dag_utils import dag_from_poset



def plot_dag(dag):
    '''
    Given a DAG instance dag, generates and shows its plot.
    '''
    G = nx.DiGraph()
    height, creator = {}, {}
    branch = {pid:{} for pid in range(dag.n_processes)}
    self_descendant, self_predecessor = {}, {}

    for unit in dag.sorted():
        # add the unit to networkx representation
        G.add_node(unit)
        creator_id = dag.pid(unit)

        # set height[unit]
        height[unit] = max([height[parent] for parent in dag.parents(unit)], default=-1) + 1

        for parent in dag.parents(unit):
            # add an edge to the networkx representation
            G.add_edge(unit, parent)

        # set self_predecessor[unit]
        self_predecessor[unit] = dag.self_predecessor(creator_id, dag.parents(unit))
        # set self_descendant
        if self_predecessor[unit]:
            predecessor = self_predecessor[unit]
            if predecessor in self_descendant:
                self_descendant[predecessor].append(unit)
            else:
                self_descendant[predecessor] = [unit]

        # set branch[creator_id][unit]
        if self_predecessor[unit] is None:
            branch[creator_id][unit] = 0
        elif len(self_descendant[self_predecessor[unit]]) == 1:
            branch[creator_id][unit] = branch[creator_id][self_predecessor[unit]]
        else:
            branch[creator_id][unit] = max(branch[creator_id].values())+1

    pos = {}

    # find positions of units in the plot
    # we plot units created by a given process vertically
    # we use height[unit] for its height in the plot
    x = dict(zip(range(dag.n_processes), np.linspace(27, 243, dag.n_processes)))
    dx = x[1]-x[0]
    for pid in range(dag.n_processes):
        units_per_pid = [unit for unit in dag if pid == dag.pid(unit)]
        x_per_pid = []
        heights = [height[unit] for unit in units_per_pid]
        err = 0
        spaces = 60 * np.array(heights) + err + 70
        y = dict(zip(units_per_pid, spaces))

        n_branches = len(set(branch[pid].values()))
        branch_x = np.linspace(-dx/2+5, dx/2-5, n_branches)
        for unit in units_per_pid:
            pos_y = y[unit]
            pos_x = x[dag.pid(unit)]
            if n_branches > 1:
                pos_x += branch_x[branch[pid][unit]]

            x_per_pid.append(pos_x)
            pos[unit] = (pos_x, pos_y)

    color_values = np.linspace(0, 1, dag.n_processes+1)[1:]
    color_map = dict(zip(range(dag.n_processes), color_values))
    color_map[-1] = 0
    node_color = [color_map[dag.pid(unit)] for unit in G.nodes()]
    nx.draw(G, pos, with_labels=True, arrows=True, node_color=node_color, node_size=1000, cmap=plt.get_cmap('jet'))
    plt.show()


def plot_poset(poset):
    '''
    Given a poset, generates and shows its plot.
    '''
    dag, _ = dag_from_poset(poset)
    plot_dag(dag)
