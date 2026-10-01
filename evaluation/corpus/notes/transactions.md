# Database transactions and recovery

Transactions use atomicity, consistency, isolation and durability. Write ahead logging persists log records before modified database pages. A committed transaction must survive a crash. Two phase locking has a growing phase that acquires locks and a shrinking phase that releases them. Serializable isolation prevents executions that cannot be equivalent to a serial order. A dirty read observes uncommitted changes. Checkpoints reduce recovery work.
