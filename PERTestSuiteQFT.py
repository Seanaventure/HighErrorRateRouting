import matplotlib.pyplot as plt
import networkx as nx
import qiskit
import PERR
from qiskit.transpiler import CouplingMap
from qiskit.transpiler.passes.routing import BasicSwap
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
for i in range(4):
    for j in range(4):
        if i is not j:
            couplingList.append([i, j])


provider = IBMQ.load_account()
backend = provider.get_backend('ibmq_lima')

basis_gates = backend.configuration().basis_gates

couplingMap = CouplingMap(couplingList)

squareCouplingList = list()
for i in range(4):
    for j in range(4):
        if i is not j:
            if abs(i-j) == 1:
                squareCouplingList.append([i, j])
squareCouplingList.append(([0, 3]))
squareCouplingList.append(([3, 0]))
squareCouplingMap = CouplingMap(squareCouplingList)

def qft_rotations(circuit, n):
    """Performs qft on the first n qubits in circuit (without swaps)"""
    if n == 0:
        return circuit
    n -= 1
    circuit.h(n)
    for qubit in range(n):
        circuit.cp(pi/2**(n-qubit), qubit, n)
    # At the end of our function, we call the same function again on
    # the next qubits (we reduced n by one earlier in the function)
    qft_rotations(circuit, n)


def swap_registers(circuit, n):
    for qubit in range(n//2):
        circuit.swap(qubit, n-qubit-1)
    return circuit


def qft(circuit, n):
    """QFT on the first n qubits in circuit"""
    qft_rotations(circuit, n)
    swap_registers(circuit, n)
    return circuit


def inverse_qft(circuit, n):
    """Does the inverse QFT on the first n qubits in circuit"""
    # First we create a QFT circuit of the correct size:
    qft_circ = qft(QuantumCircuit(n), n)
    # Then we take the inverse of this circuit
    invqft_circ = qft_circ.inverse()
    # And add it to the first n qubits in our existing circuit
    circuit.append(invqft_circ, circuit.qubits[:n])
    return circuit.decompose()  # .decompose() allows us to see the individual gates


# Let's see how it looks:
circuit = QuantumCircuit(4)
circuit.x(0)
circuit.x(3)
qft(circuit, 4)
circuit = inverse_qft(circuit, 4)
circuit.measure_all()
#print(circuit)

#circuit.draw(output="mpl", filename="QftResults/qftCircuit.png")
s = '1001'

circDag = circuit_to_dag(circuit)

for i in range(100):

    # Create a noise model for the simulations
    noise_model = noise.NoiseModel()
    #0.15, 0.02, 0.09, 0.04, 0.05, 0.01 
    err1Rate, err2Rate, err3Rate, err4Rate, err5Rate, err6Rate = random.randrange(1, 20, 1)/100.0, random.randrange(1, 20, 1)/100.0, \
        random.randrange(1, 20, 1)/100.0, random.randrange(1, 20, 1)/100.0, random.randrange(1, 20, 1)/100.0, random.randrange(1, 20, 1)/100.0
    error_1 = noise.depolarizing_error(err1Rate, 2)
    error_2 = noise.depolarizing_error(err2Rate, 2)
    error_3 = noise.depolarizing_error(err3Rate, 2)
    error_4 = noise.depolarizing_error(err4Rate, 2)
    error_5 = noise.depolarizing_error(err5Rate, 2)
    error_6 = noise.depolarizing_error(err6Rate, 2)

    noise_model.add_quantum_error(error_1, ['cx'], [0, 1])
    noise_model.add_quantum_error(error_2, ['cx'], [1, 2])
    noise_model.add_quantum_error(error_3, ['cx'], [0, 2])
    noise_model.add_quantum_error(error_4, ['cx'], [1, 3])
    noise_model.add_quantum_error(error_5, ['cx'], [2, 3])
    noise_model.add_quantum_error(error_6, ['cx'], [0, 3])

    # Generate a noise graph to pass into PERR
    noiseGraph = nx.Graph()
    noiseGraph.add_nodes_from([0, 2])
    noiseGraph.add_edge(0, 1, weight=1.0-err1Rate)
    noiseGraph.add_edge(1, 2, weight=1.0-err2Rate)
    noiseGraph.add_edge(0, 2, weight=1.0-err3Rate)
    noiseGraph.add_edge(1, 3, weight=1.0-err4Rate)
    noiseGraph.add_edge(2, 3, weight=1.0-err5Rate)
    noiseGraph.add_edge(0, 3, weight=1.0-err6Rate)

    perr = PERR.PERR(squareCouplingMap, noiseGraph)
    basSwap = BasicSwap(squareCouplingMap)

    #print(squareCouplingMap)
    # Run PERR
    perrRes = perr.run(circDag)
    updatedCirc = dag_to_circuit(perrRes)

    bSwapRes = basSwap.run(circDag)
    bSwapCirc = dag_to_circuit(bSwapRes)

    # Transpile PERR
    transpiledPERR = transpile(updatedCirc, Aer.get_backend('qasm_simulator'),
                                 coupling_map=squareCouplingMap,
                                 basis_gates=basis_gates,
                                 routing_method='basic',
                                 layout_method='trivial')

    # Transpile non PERR
    transpiledNormal = transpile(bSwapCirc, Aer.get_backend('qasm_simulator'),
                                 coupling_map=squareCouplingMap,
                                 basis_gates=basis_gates,
                                 routing_method='basic',
                                 layout_method='trivial')

    sim = Aer.get_backend('qasm_simulator')

    simResultPERR = sim.run(transpiledPERR, noise_model=noise_model).result()
    simResultNonPERR = sim.run(transpiledNormal, noise_model=noise_model).result()

    # simResultPERR = execute(updatedCirc, Aer.get_backend('qasm_simulator'),
    #                            coupling_map=couplingMap,
    #                            basis_gates=basis_gates,
    #                            noise_model=noise_model).result()
    # simResultNonPERR = execute(circuit, Aer.get_backend('qasm_simulator'),
    #                            coupling_map=couplingMap,
    #                            basis_gates=basis_gates,
    #                            noise_model=noise_model).result()
    # Output file and print results
    fName = "perrQFTCouplingOutputs/PERRCirc" + str(i) + ".png"
    fName2 = "perrQFTCouplingOutputs/NonCirc" + str(i) + ".png"
    #updatedCirc.draw(output='mpl', filename=fName)
    #bSwapCirc.draw(output='mpl', filename=fName2)
    if transpiledNormal != transpiledPERR:
        print("CIRCUIT CHANGED")
        #updatedCirc.draw(output='mpl', filename=fName)
        #bSwapCirc.draw(output='mpl', filename=fName2)
        print("Iter: " + str(i) + " ErrorRate of edges (0,1) (1, 2), (0, 2), (1, 3), (2, 3), (0, 3) counts for perr/nonPerr:")
        print(str(err1Rate) + " " + str(err2Rate) + " " + str(err3Rate) + " " + str(err4Rate) + " " + str(err5Rate) + " " + str(err6Rate))
        print(str(simResultPERR.get_counts()[s]) + " " + str(simResultNonPERR.get_counts()[s]))
        print("----------------------")



