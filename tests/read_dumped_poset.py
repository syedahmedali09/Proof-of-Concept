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

from aleph.utils import dag_utils
import time, os, sys
import random

# path to a file with a dag dumped from poset using the dump_to_file() method
file_name = 'poset_1.dag'
if len(sys.argv) > 1:
    file_name = sys.argv[1]

if not os.path.exists(file_name):
    print(f"The file {file_name} doesn't exist. Aborting.")
    exit(0)


dag = dag_utils.dag_from_file(file_name)
print(f"Dag consists of {len(dag)} units.")
# retrieve the list of units in the same order as they were added to the poset
units_list = dag.get_node_list_as_added()

print("level   (pr. units)   (min pr. units)  (avg n vis. below)")
for level in range(1000):
    primes = dag.get_prime_units_by_level(level)
    if primes == []:
        break
    min_primes = [U for U in primes if all(dag.level(V) < dag.level(U) for V in dag.parents(U))]

    n_visible_below = []
    for U in primes:
        below = dag.get_prime_units_by_level(level-1)
        cnt = sum(dag.is_reachable(V, U) for V in below)
        n_visible_below.append(cnt)

    avg_n_visible = sum(n_visible_below)/len(n_visible_below)
    print(f"{level: <15} {len(primes): <15} {len(min_primes): <15}  {avg_n_visible:<15.2f}")


for U in units_list:
    parents = dag.parents(U)
    if parents != []:
        self_predecessor = parents[0]
        level_now = dag.level(U)
        level_prev = dag.level(self_predecessor)
        if level_now - level_prev > 1:
            creator_id = dag.pid(U)
            print(f"Process {creator_id} jumped from level {level_prev} to {level_now}.")


tries = 10**4
timer_start = time.time()
for _ in range(tries):
    U1 = random.choice(units_list)
    U2 = random.choice(units_list)
    res = dag.is_reachable(U1, U2)

timer_stop = time.time()
print(f"Executed {tries} random below queries, total time {timer_stop - timer_start:.4f}")

for U in units_list:
    if dag.get_node_info(U, "timing"):
        print(U, "is the timing unit at level", dag.level(U))

