from fileinput import filename
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

qc = QuantumCircuit(4)
qc.x(0)
qc.x(1)
qc.ccx(0, 1, 2)
qc.measure_all()
qc = qc.decompose()
circDag = circuit_to_dag(qc)


# Generate a noise graph to pass into PERR
noiseGraph = nx.Graph()
noiseGraph.add_nodes_from([0, 2])
noiseGraph.add_edge(0, 1, weight=0.99)
noiseGraph.add_edge(0, 3, weight=0.99)
noiseGraph.add_edge(1, 2, weight=0.99)
noiseGraph.add_edge(2, 3, weight=0.99)
perr = PERR.PERR(squareCouplingMap, noiseGraph)

qc.draw(output='mpl', filename='CircTestBefore.png')
# Run PERR
perrRes = perr.run(circDag)
updatedCirc = dag_to_circuit(perrRes)

updatedCirc.draw(output='mpl', filename='CircTest.png')