import logging
from copy import copy
from itertools import cycle
import numpy as np
import networkx as nx

from qiskit.dagcircuit import DAGCircuit
from qiskit.circuit.library.standard_gates import SwapGate
from qiskit.transpiler.basepasses import TransformationPass
from qiskit.transpiler.exceptions import TranspilerError
from qiskit.transpiler.layout import Layout
from qiskit.dagcircuit import DAGNode

class PERR(TransformationPass):

    def __init__(self, couplingMap, qubitAccuracy, initial_layout=None, searchDepth=2):
        super().__init__()
        self.couplingMap = couplingMap
        self.qubitAccuracy = qubitAccuracy
        self.initial_layout = initial_layout
        self.searchDepth = searchDepth

    def run(self, dag):
        new_dag = DAGCircuit()
        for qreg in dag.qregs.values():
            new_dag.add_qreg(qreg)
        for creg in dag.cregs.values():
            new_dag.add_creg(creg)

        if self.initial_layout is None:
            if self.property_set["layout"]:
                self.initial_layout = self.property_set["layout"]
            else:
                self.initial_layout = Layout.generate_trivial_layout(*dag.qregs.values())

        if len(dag.qubits) != len(self.initial_layout):
            raise TranspilerError('The layout does not match the amount of qubits in the DAG')

        if len(self.couplingMap.physical_qubits) != len(self.initial_layout):
            raise TranspilerError(
                "Mappers require to have the layout to be the same size as the coupling map")
        
        canonical_register = dag.qregs['q']
        trivial_layout = Layout.generate_trivial_layout(canonical_register)
        current_layout = trivial_layout.copy()

        for layer in dag.serial_layers():
            subdag = layer['graph']
            for gate in subdag.two_qubit_ops():
                physQArgs = [current_layout[gate.qargs[0]], current_layout[gate.qargs[1]]]

                if self.couplingMap.distance(physQArgs[0], physQArgs[1]) != 1:
                    # If we can perform no noise based swaps, make sure the qubits are connecting in the coupling map
                    # This routing algorithm is taken form the basic_swap.py module in Qiskit terra
                    # Insert a new layer with the SWAP(s).
                    swap_layer = DAGCircuit()
                    swap_layer.add_qreg(canonical_register)

                    path = self.couplingMap.shortest_undirected_path(physQArgs[0], physQArgs[1])
                    for swap in range(len(path) - 2):
                        connected_wire_1 = path[swap]
                        connected_wire_2 = path[swap + 1]

                        qubit_1 = current_layout[connected_wire_1]
                        qubit_2 = current_layout[connected_wire_2]

                        #print("ROUTING SWAP BETWEEN PHYSICAL QUBITS (" + str(connected_wire_1) + ", " + str(connected_wire_2) + "), log qubits (" + str(qubit_1) + ", " + str(qubit_2) + ")")
                        # create the swap operation
                        swap_layer.apply_operation_back(
                            SwapGate(), qargs=[qubit_1, qubit_2], cargs=[]
                        )

                    # layer insertion
                    order = current_layout.reorder_bits(new_dag.qubits)
                    new_dag.compose(swap_layer, qubits=order)

                    # update current_layout
                    for swap in range(len(path) - 2):
                        current_layout.swap(path[swap], path[swap + 1])       
                else:
                #print(current_layout)
                    # If the two qubits are not attached at the coupling map add swap to connect
                    betterEdge = self.find_better_link(physQArgs[0], physQArgs[1], current_layout, self.searchDepth)
                    if betterEdge is not None:
                        # Lets insert swap to go to the better edge
                        swap_layer = DAGCircuit()
                        swap_layer.add_qreg(canonical_register)

                        swapPath = self.find_shortest_path((physQArgs[0], physQArgs[1]), (betterEdge[0], betterEdge[1]))
                        for i in range(2):
                            if swapPath[i] is not None:
                                for swap in range(0, len(swapPath[i])-1, 1):
                                        connected_wire_1 = swapPath[i][swap]
                                        connected_wire_2 = swapPath[i][swap + 1]

                                        qubit_1 = current_layout[connected_wire_1]
                                        qubit_2 = current_layout[connected_wire_2]
                                        #print("NOISE SWAP BETWEEN PHYSICAL QUBITS (" + str(connected_wire_1) + ", " + str(connected_wire_2) + "), log qubits (" + str(qubit_1) + ", " + str(qubit_2) + ")")

                                        swap_layer.apply_operation_back(SwapGate(),
                                                                            qargs=[qubit_1, qubit_2],
                                                                            cargs=[])

                        # layer insertion
                        order = current_layout.reorder_bits(new_dag.qubits)
                        new_dag.compose(swap_layer, qubits=order)

                        # update current_layout
                        for i in range(2):
                            if swapPath[i] is not None:
                                for swap in range(0, len(swapPath[i])-1, 1):
                                    current_layout.swap(swapPath[i][swap], swapPath[i][swap + 1])  
                            
            order = current_layout.reorder_bits(new_dag.qubits)
            new_dag.compose(subdag, qubits=order)

        return new_dag

    def find_better_link(self, qubit1, qubit2, currentLayout, depth):
        """
        Given two qubits that will be used, it finds are more ideal pair given the
        coupling map

        Args:
            qubit1: First physical qubit being used in gate
            qubit2: Second physical qubit being used in gate
        """
        
        # Gather a list of the edges
        # Annoyingly, the get_edges functions will return 2 times the number of edges
        # ie, it returns [0,1] and [1,0] as two different edges. This confuses the algorithm
        # so we basically remove duplicates by sorting then adding to a set.
        edges = self.couplingMap.get_edges()
        uniqueEdges = set()
        for edge in edges:
            uniqueEdges.add(tuple(sorted(edge)))
        if [qubit1, qubit2] in self.qubitAccuracy.edges():
            bestEdgeAccuracy =  self.qubitAccuracy.edges[qubit1, qubit2]['weight']
        else:
            bestEdgeAccuracy = 0
            
        bestEdge = (qubit1, qubit2)
        foundBetterEdge = False
        for edge in uniqueEdges:
            if (self.couplingMap.distance(qubit1, edge[0]) <= depth and self.couplingMap.distance(qubit1, edge[1]) <= depth
                and self.couplingMap.distance(qubit2, edge[0]) <= depth and self.couplingMap.distance(qubit2, edge[1]) <= depth):
                newLinkAccuracy = self.calc_path_accuracy(bestEdge, edge, currentLayout)
                if newLinkAccuracy > bestEdgeAccuracy:
                    bestEdgeAccuracy = newLinkAccuracy
                    bestEdge = edge
                    foundBetterEdge = True
        if foundBetterEdge == False:
            bestEdge = None
        return bestEdge

    def find_path_excluding(self, sourceQubit, destQubit, exQubit):
        # Get a subgraph of coupling map without Ex qubit, find shortest path
        if sourceQubit == destQubit:
            return None 
        reducedCouplingGraph = nx.Graph()
        subGraphEdges = list()
        couplingMapEdges = self.couplingMap.get_edges()
        for edge in couplingMapEdges:
            if exQubit not in edge:
                subGraphEdges.append(edge)
        reducedCouplingGraph.add_edges_from(subGraphEdges)
        shortestPath = nx.shortest_path(reducedCouplingGraph, sourceQubit, destQubit) 
        return shortestPath


    def find_shortest_path(self, sourceQubits, destQubit):
        qubitPath = [None, None]
        #sourceQubits.sort()
        #destQubit.sort()
        q0Paths = [None, None]
        q1Paths = [None, None]
        
        if destQubit[0] != sourceQubits[1]:
            q0Paths[0] = self.find_path_excluding(sourceQubits[0], destQubit[0], sourceQubits[1])
        if destQubit[1] != sourceQubits[1]:
            q0Paths[1] = self.find_path_excluding(sourceQubits[0], destQubit[1], sourceQubits[1])

        if destQubit[0] != sourceQubits[0]:
            q1Paths[0] = self.find_path_excluding(sourceQubits[1], destQubit[0], sourceQubits[0])
        if destQubit[1] != sourceQubits[0]:
            q1Paths[1] = self.find_path_excluding(sourceQubits[1], destQubit[1], sourceQubits[0])

        if sourceQubits[0] not in destQubit and sourceQubits[1] not in destQubit:

            if len(q0Paths[0]) <= len(q1Paths[0]):
                qubitPath[0] = q0Paths[0]
                qubitPath[1] = q1Paths[1]
            else:
                qubitPath[0] = q0Paths[1]
                qubitPath[1] = q1Paths[0]

            # if len(q0Paths[1]) < len(q1Paths[1]):
            #     if len(qubitPath[0]) > len(q0Paths[1]):
            #         qubitPath[0] = q0Paths[1]
            # else:
            #     if len(qubitPath[1]) > len(q1Paths[1]):
            #         qubitPath[1] = q0Paths[1]

            if len(q0Paths[1]) < len(q0Paths[0]) and len(q0Paths[1]) < len(q1Paths[1]):
                qubitPath[0] = q0Paths[1]
            else:
                qubitPath[0] = q0Paths[0]

            if len(q1Paths[1]) < len(q1Paths[0]) and len(q1Paths[1]) < len(q0Paths[1]):
                qubitPath[1] = q1Paths[1]
            else:
                qubitPath[1] = q1Paths[0]
        elif sourceQubits[0] not in destQubit:
            # If only qubit 0 is not in destination, we only need to swap to whatever isn't the other qubit
            # ie, if we need to go from [1, 0] to [2, 0], we only need to swap from qubits 1 to 2 
            if sourceQubits[1] is not destQubit[0]:
                qubitPath[0] = q0Paths[1]
            else:
                qubitPath[0] = q0Paths[0]
        elif sourceQubits[1] not in destQubit:
            # If only qubit 1 is not in destination, we only need to swap to whatever isn't the other qubit
            # ie, if we need to go from [0, 1] to [0, 2], we only need to swap from qubits 1 to 2 
            if sourceQubits[0] is not destQubit[0]:
                qubitPath[1] = q1Paths[0]
            else:
                qubitPath[1] = q1Paths[1]
        return qubitPath
        
    def calc_path_accuracy(self, sourceQubits, destQubit, current_layout):
        # Determines accuracy of a path from an old link to a new link
        # Error rate of new link: = (EnewLink)*(Error of Path for qubit 0^3)*(Error of Path for qubit 1^3)
        # Cube is used for paths since each swap is 3 CNOT gates

        # represents the paths needed for source qubits 0 and 1
        qubitPath = self.find_shortest_path(sourceQubits, destQubit)
        
        if qubitPath[0] is None and qubitPath[1] is None:
            return 0

        qubitPathAccuracy = [1.0, 1.0]

        for i in range(2):
            if qubitPath[i] is not None:
                for swap in range(0, len(qubitPath[i])-1, 1):
                    connected_wire_1 = qubitPath[i][swap]
                    connected_wire_2 = qubitPath[i][swap + 1]

                    # qubit_1 = current_layout[connected_wire_1]
                    # qubit_2 = current_layout[connected_wire_2]

                    linkError = self.qubitAccuracy.edges[connected_wire_1, connected_wire_2]['weight']
                    qubitPathAccuracy[i] = qubitPathAccuracy[i] * (linkError**3)

        opAccuracy = self.qubitAccuracy.edges[destQubit[0], destQubit[1]]['weight']
        return opAccuracy*qubitPathAccuracy[0]*qubitPathAccuracy[1]



