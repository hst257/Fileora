# Virtual memory and paging

Paging divides virtual memory into fixed-size pages and physical memory into frames. A page table maps virtual page numbers to physical frame numbers. The translation lookaside buffer caches recently used translations. A page fault occurs when a referenced page is not present in physical memory. The operating system loads it from backing storage. Least recently used replacement evicts the page unused for the longest time. Demand paging loads pages only when accessed.
