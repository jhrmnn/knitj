from graphviz import Digraph


g = Digraph(format='svg')
g.node('N', 'Notebook')
g.node('K', 'Kernel')
g.node('R', 'Renderer')
g.node('S', 'Source')
g.node('W', 'WebServer')
g.edges('NK KR RN SR SK WR'.split())
g.render('../static/graph.gv')
