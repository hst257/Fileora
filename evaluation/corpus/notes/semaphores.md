# Semaphore synchronization

A semaphore is a counter used to coordinate concurrent threads. The wait operation decrements the counter and may block. The signal operation increments the counter and wakes a waiting thread. A binary semaphore protects a critical section. Counting semaphores manage multiple available resources. A mutex has ownership semantics; a semaphore can be signaled by another thread. Deadlocks can occur when threads hold resources while waiting for others.
