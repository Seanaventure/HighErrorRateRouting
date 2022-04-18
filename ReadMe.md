### High error rate routing
This is the folder for high error rate routing. There are two main benchmarks, accuracy and compilation time benchmarks.
Accuracy benchmarks take each circuit and run it 200 times with random noise and look at the percentage of time the correct result was obtained
compilation time benchmarks time how long compilation took.
For accuracy benchmarks, HERRTestSuiteBv.py is the most well commented. All other are just copy paste of that.
HERR.py is the main routing algorithm

To run this all, you just need qiskit installed

To run a benchmark, its just: 
python Benchmarkname.py

That said, it outputs a ton of text so I like to pipe it to a file like
python Benchmarkname.py > testResults.txt
