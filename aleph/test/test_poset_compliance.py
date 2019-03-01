from aleph.data_structures import Unit, Poset
from aleph.utils import dag_utils
import random
import pytest


def check_compliance_vs_pattern(dag, topological_list, pattern, compliance_rules = None):
    unit_dict = {}
    poset = Poset(n_processes = dag.n_processes, compliance_rules = compliance_rules, use_tcoin = False)

    for node, answer in zip(topological_list, pattern):
        U = Unit(creator_id = dag.pid(node), parents = [unit_dict[parent] for parent in dag.parents(node)], txs = [])
        unit_dict[node] = U
        poset.prepare_unit(U)
        assert poset.check_compliance(U) == answer, f"Node {node} was problematic."
        poset.add_unit(U)



def test_small_random_compliance():
    random.seed(123456789)
    repetitions = 800
    properties = ['expand_primes']
    for violated_property in properties:
        for rep in range(repetitions):
            n_processes = random.randint(4, 5)
            n_units = random.randint(0, n_processes*2)
            if violated_property == 'forker_muting':
                n_forkers = random.randint(1, n_processes)
            else:
                n_forkers = random.randint(0, n_processes)
            constraints_ensured = {property : True for property in properties}
            constraints_ensured['distinct_parents'] = True
            constraints_ensured['forker_muting'] = True
            constraints_violated = {violated_property  : False}
            constraints_violated['distinct_parents'] = True
            constraints_violated['forker_muting'] = True
            dag, topological_list = dag_utils.generate_random_violation(n_processes, n_units, n_forkers,
                                    constraints_ensured, constraints_violated)
            pattern = [True] * len(topological_list)
            pattern[-1] = False
            check_compliance_vs_pattern(dag, topological_list, pattern)

def test_small_random_legacy_compliance():
    random.seed(123456789)
    repetitions = 800
    properties = ['forker_muting', 'growth', 'parent_diversity']
    for violated_property in properties:
        for rep in range(repetitions):
            n_processes = random.randint(4, 5)
            n_units = random.randint(0, n_processes*2)
            if violated_property == 'forker_muting':
                n_forkers = random.randint(1, n_processes)
            else:
                n_forkers = random.randint(0, n_processes)
            constraints_ensured = {property : True for property in properties}
            constraints_ensured['distinct_parents'] = True
            constraints_violated = {violated_property  : False}
            constraints_violated['distinct_parents'] = True
            dag, topological_list = dag_utils.generate_random_violation(n_processes, n_units, n_forkers,
                                    constraints_ensured, constraints_violated)
            pattern = [True] * len(topological_list)
            pattern[-1] = False
            check_compliance_vs_pattern(dag, topological_list, pattern, compliance_rules = {'parent_diversity': True, 'growth': True, 'expand_primes': False})


def test_large_random_compliance():
    random.seed(123456789)
    repetitions = 20
    properties = ['expand_primes']
    for violated_property in properties:
        for rep in range(repetitions):
            n_processes = random.randint(30, 80)
            n_units = random.randint(0, n_processes*2)
            if violated_property == 'forker_muting':
                n_forkers = random.randint(1, n_processes//3)
            else:
                n_forkers = random.randint(0, n_processes//3)
            constraints_ensured = {property : True for property in properties}
            constraints_ensured['distinct_parents'] = True
            constraints_ensured['forker_muting'] = True
            constraints_violated = {violated_property  : False}
            constraints_violated['distinct_parents'] = True
            constraints_violated['forker_muting'] = True
            dag, topological_list = dag_utils.generate_random_violation(n_processes, n_units, n_forkers,
                                    constraints_ensured, constraints_violated)
            pattern = [True] * len(topological_list)
            pattern[-1] = False
            check_compliance_vs_pattern(dag, topological_list, pattern)

def test_large_random_legacy_compliance():
    random.seed(123456789)
    repetitions = 20
    properties = ['forker_muting', 'growth', 'parent_diversity']
    for violated_property in properties:
        for rep in range(repetitions):
            n_processes = random.randint(30, 80)
            n_units = random.randint(0, n_processes*2)
            if violated_property == 'forker_muting':
                n_forkers = random.randint(1, n_processes)
            else:
                n_forkers = random.randint(0, n_processes)
            constraints_ensured = {property : True for property in properties}
            constraints_ensured['distinct_parents'] = True
            constraints_violated = {violated_property  : False}
            constraints_violated['distinct_parents'] = True
            dag, topological_list = dag_utils.generate_random_violation(n_processes, n_units, n_forkers,
                                    constraints_ensured, constraints_violated)
            pattern = [True] * len(topological_list)
            pattern[-1] = False
            check_compliance_vs_pattern(dag, topological_list, pattern, compliance_rules = {'parent_diversity': True, 'growth': True, 'expand_primes': False})
