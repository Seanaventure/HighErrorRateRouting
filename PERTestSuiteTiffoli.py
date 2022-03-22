import PERR
import matplotlib.pyplot as plt
import networkx as nx
import qiskit
from qiskit.transpiler import CouplingMap
from qiskit import QuantumCircuit, execute, Aer, IBMQ
from qiskit.dagcircuit import DAGCircuit
from qiskit.converters import circuit_to_dag
from qiskit.converters import dag_to_circuit
from math import pi
from qiskit.compiler import transpile, assemble
from qiskit.providers.aer.noise import NoiseModel
import qiskit.providers.aer.noise as noise
from qiskit.tools.visualization import dag_drawer
import random



couplingList = list()
for i in range(3):
    for j in range(3):
        if i is not j:
            couplingList.append([i, j])

squareCouplingList = list()
for i in range(4):
    for j in range(4):
        if i is not j:
            if abs(i-j) == 1:
                squareCouplingList.append([i, j])
squareCouplingList.append(([0, 3]))
squareCouplingList.append(([3, 0]))
provider = IBMQ.load_account()
backend = provider.get_backend('ibmq_lima')

basis_gates = backend.configuration().basis_gates

squareCouplingMap = CouplingMap(squareCouplingList)
couplingMap = CouplingMap(couplingList)

qcPERR = QuantumCircuit(3)
qcPERR.x(0)
qcPERR.x(1)
qcPERR.ccx(0, 1, 2)
qcPERR.measure_all()
qcPERR = qcPERR.decompose()
nonPERR = QuantumCircuit(3)
nonPERR.x(0)
nonPERR.x(1)
nonPERR.ccx(0, 1, 2)
nonPERR.measure_all()
circDag = circuit_to_dag(qcPERR)

for i in range(40):

    # Create a noise model for the simulations
    noise_model = noise.NoiseModel()
    err1Rate, err2Rate, err3Rate = random.randrange(1, 20, 1)/100.0, random.randrange(1, 20, 1)/100.0, random.randrange(1, 20, 1)/100.0
    error_1 = noise.depolarizing_error(err1Rate, 2)
    error_2 = noise.depolarizing_error(err2Rate, 2)
    error_3 = noise.depolarizing_error(err3Rate, 2)
    noise_model.add_quantum_error(error_1, ['cx'], [0, 1])
    noise_model.add_quantum_error(error_2, ['cx'], [1, 2])
    noise_model.add_quantum_error(error_3, ['cx'], [0, 2])

    # Generate a noise graph to pass into PERR
    noiseGraph = nx.Graph()
    noiseGraph.add_nodes_from([0, 2])
    noiseGraph.add_edge(0, 1, weight=1.0-err1Rate)
    noiseGraph.add_edge(1, 2, weight=1.0-err2Rate)
    noiseGraph.add_edge(0, 2, weight=1.0-err3Rate)
    perr = PERR.PERR(couplingMap, noiseGraph)

    # Run PERR
    perrRes = perr.run(circDag)
    updatedCirc = dag_to_circuit(perrRes)
    if updatedCirc != qcPERR:
        print("CIRCUIT CHANGED")

    simResultPERR = execute(updatedCirc, Aer.get_backend('qasm_simulator'),
                               coupling_map=couplingMap,
                               basis_gates=basis_gates,
                               noise_model=noise_model).result()
    simResultNonPERR = execute(nonPERR, Aer.get_backend('qasm_simulator'),
                               coupling_map=couplingMap,
                               basis_gates=basis_gates,
                               noise_model=noise_model).result()
    # Output file and print results
    fName = "perrOutputs/PERRCirc" + str(i) + ".png"
    #updatedCirc.draw(output='mpl', filename=fName)
    print("Iter: " + str(i) + " ErrorRate of edges (0,1) (0, 2), (1, 2), counts for perr/nonPerr:")
    print(str(err1Rate) + " " + str(err2Rate) + " " + str(err3Rate))
    print(str(simResultPERR.get_counts()['111']) + " " + str(simResultNonPERR.get_counts()['111']))
    print("----------------------")



