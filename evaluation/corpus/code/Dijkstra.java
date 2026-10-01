import java.util.*;
/** Dijkstra shortest paths with nonnegative edge weights and a priority queue. */
public class Dijkstra {
    public static int[] shortestPaths(List<int[]>[] graph, int source) {
        int[] distance = new int[graph.length];
        Arrays.fill(distance, Integer.MAX_VALUE);
        distance[source] = 0;
        PriorityQueue<int[]> queue = new PriorityQueue<>(Comparator.comparingInt(a -> a[1]));
        queue.add(new int[]{source, 0});
        while (!queue.isEmpty()) {
            int[] current = queue.poll();
            if (current[1] != distance[current[0]]) continue;
            for (int[] edge : graph[current[0]]) {
                int candidate = current[1] + edge[1];
                if (candidate < distance[edge[0]]) {
                    distance[edge[0]] = candidate;
                    queue.add(new int[]{edge[0], candidate});
                }
            }
        }
        return distance;
    }
}
