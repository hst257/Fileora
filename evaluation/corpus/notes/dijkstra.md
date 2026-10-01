# Dijkstra shortest path implementation

Dijkstra computes shortest paths for graphs with nonnegative edge weights. The algorithm maintains tentative distances and extracts the smallest distance from a priority queue. Relaxing an edge updates a neighbor when a cheaper route is found. An adjacency list stores outgoing weighted edges. Negative edges violate the greedy assumption. With a binary heap, runtime is O((V plus E) log V). The Java implementation uses PriorityQueue and an array of distances.
