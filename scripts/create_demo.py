"""Create authored, redistributable fixtures and fixed retrieval judgments."""

from __future__ import annotations

import argparse
import hashlib
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

TOPICS = [
    (
        "semaphores",
        "Semaphore synchronization",
        "A semaphore is a counter used to coordinate concurrent threads. The wait operation decrements the counter and may block. The signal operation increments the counter and wakes a waiting thread. A binary semaphore protects a critical section. Counting semaphores manage multiple available resources. A mutex has ownership semantics; a semaphore can be signaled by another thread. Deadlocks can occur when threads hold resources while waiting for others.",
        [
            "semaphore wait and signal",
            "Find my notes about semaphores",
            "How can threads protect a critical section?",
            "binary semaphore versus mutex ownership",
            "counting semaphore available resources",
            "wake a waiting thread",
            "counter synchronization between threads",
            "Where did I write about critical section protection?",
            "Notes discussing semaphore deadlocks",
        ],
    ),
    (
        "paging",
        "Virtual memory and paging",
        "Paging divides virtual memory into fixed-size pages and physical memory into frames. A page table maps virtual page numbers to physical frame numbers. The translation lookaside buffer caches recently used translations. A page fault occurs when a referenced page is not present in physical memory. The operating system loads it from backing storage. Least recently used replacement evicts the page unused for the longest time. Demand paging loads pages only when accessed.",
        [
            "virtual memory page table",
            "Find the notes where paging was explained",
            "How are virtual addresses mapped to physical frames?",
            "translation lookaside buffer cache",
            "page fault backing storage",
            "least recently used replacement",
            "demand paging only when accessed",
            "Where did I discuss memory frames?",
            "A referenced page is not present in RAM",
        ],
    ),
    (
        "scheduling",
        "CPU process scheduling",
        "Round robin CPU scheduling gives each runnable process a time quantum. Preemption switches the running process when its quantum expires. Shortest job first chooses the process with the smallest predicted CPU burst. Priority scheduling may starve low-priority processes; aging gradually increases their priority. Waiting time measures time spent in the ready queue. Turnaround time is completion time minus arrival time. Context switching has overhead.",
        [
            "round robin time quantum",
            "Find process scheduling notes",
            "Which scheduler rotates runnable processes?",
            "shortest job first CPU burst",
            "priority scheduling aging starvation",
            "waiting time ready queue",
            "turnaround completion arrival time",
            "preempt a process when quantum expires",
            "context switching overhead",
        ],
    ),
    (
        "normalization",
        "Database normalization assignment",
        "Database normalization reduces redundant data and update anomalies. A functional dependency means one attribute set determines another. Second normal form removes partial dependencies on a composite key. Third normal form removes transitive dependencies. Boyce Codd normal form requires every determinant to be a candidate key. Our assignment decomposed StudentEnrollment into Student, Course and Enrollment tables. Lossless decomposition preserves the original relation when joined.",
        [
            "database normalization assignment",
            "Find my notes about third normal form",
            "How do we remove update anomalies?",
            "functional dependency determinant",
            "second normal form composite key",
            "Boyce Codd candidate key",
            "StudentEnrollment decomposition",
            "lossless relation join",
            "remove transitive dependencies",
        ],
    ),
    (
        "transactions",
        "Database transactions and recovery",
        "Transactions use atomicity, consistency, isolation and durability. Write ahead logging persists log records before modified database pages. A committed transaction must survive a crash. Two phase locking has a growing phase that acquires locks and a shrinking phase that releases them. Serializable isolation prevents executions that cannot be equivalent to a serial order. A dirty read observes uncommitted changes. Checkpoints reduce recovery work.",
        [
            "write ahead logging recovery",
            "Find ACID transaction notes",
            "How does a committed transaction survive a crash?",
            "two phase locking growing shrinking",
            "serializable isolation serial order",
            "dirty read uncommitted changes",
            "database recovery checkpoint",
            "atomicity consistency isolation durability",
            "log records before modified pages",
        ],
    ),
    (
        "load_balancing",
        "AWS application load balancing",
        "An AWS Application Load Balancer routes HTTP requests to target groups. Listener rules support host based and path based routing. Target health checks remove unhealthy instances from request rotation. Auto Scaling adjusts the number of EC2 instances based on load. An application load balancer operates at layer seven. A network load balancer serves transport level TCP traffic. Sticky sessions keep a client associated with a target but may skew load distribution.",
        [
            "AWS load balancing target groups",
            "Find documents where I discussed AWS load balancing",
            "How do unhealthy EC2 instances stop receiving requests?",
            "host based path based listener rules",
            "layer seven application load balancer",
            "network load balancer TCP traffic",
            "Auto Scaling instances based on load",
            "sticky sessions load distribution",
            "HTTP requests routed to target groups",
        ],
    ),
    (
        "networking",
        "Computer networks TCP and DNS",
        "TCP provides reliable ordered delivery through acknowledgements and retransmissions. Its three way handshake exchanges SYN, SYN ACK and ACK messages. Congestion control reduces the sending rate when the network is overloaded. DNS resolves domain names into IP addresses. Recursive resolvers cache answers according to a time to live. UDP sends datagrams without delivery guarantees and is suitable for latency-sensitive applications.",
        [
            "TCP three way handshake",
            "Find computer network protocol notes",
            "How are lost packets retransmitted?",
            "DNS recursive resolver cache",
            "domain names to IP addresses",
            "UDP delivery guarantees",
            "congestion control sending rate",
            "SYN ACK handshake messages",
            "time to live DNS answers",
        ],
    ),
    (
        "dijkstra",
        "Dijkstra shortest path implementation",
        "Dijkstra computes shortest paths for graphs with nonnegative edge weights. The algorithm maintains tentative distances and extracts the smallest distance from a priority queue. Relaxing an edge updates a neighbor when a cheaper route is found. An adjacency list stores outgoing weighted edges. Negative edges violate the greedy assumption. With a binary heap, runtime is O((V plus E) log V). The Java implementation uses PriorityQueue and an array of distances.",
        [
            "Dijkstra priority queue shortest path",
            "Where is my Java implementation of Dijkstra?",
            "Find the algorithm for cheapest routes with nonnegative weights",
            "graph edge relaxation tentative distance",
            "adjacency list weighted edges",
            "negative edges greedy assumption",
            "Java PriorityQueue distances",
            "binary heap shortest path runtime",
            "extract smallest distance neighbor update",
        ],
    ),
    (
        "retrieval",
        "Semantic search engineering",
        "Semantic search converts queries and passages into dense embeddings. Normalized vectors can be ranked by cosine similarity using an inner product. BM25 ranks lexical matches using term frequency and inverse document frequency. Reciprocal rank fusion combines ranked candidate lists without adding incompatible raw scores. Metadata filters restrict eligible documents before retrieval. A cross encoder reranks a small candidate set using query and passage pairs.",
        [
            "reciprocal rank fusion retrieval",
            "Find my notes about semantic embeddings",
            "Why should I normalize vectors for cosine search?",
            "BM25 term frequency inverse document frequency",
            "cross encoder query passage pairs",
            "metadata eligible documents before retrieval",
            "dense embedding natural language query",
            "incompatible raw ranking scores",
            "rerank a small candidate set",
        ],
    ),
    (
        "testing",
        "Software testing and cache invalidation",
        "Unit tests check individual behaviors while integration tests verify component interaction. Deterministic fixtures make failures reproducible. A regression test prevents a previously fixed bug from returning. Content hashes invalidate cached processing when source bytes change. Idempotent indexing can repeat a job without creating duplicate evidence. Crash recovery rebuilds derived indexes from authoritative database records. Filesystem watchers can miss events, so periodic reconciliation scans verify the catalog.",
        [
            "idempotent indexing duplicate evidence",
            "Find my notes about regression tests",
            "How do content hashes invalidate cached processing?",
            "unit versus integration tests",
            "rebuild derived indexes crash recovery",
            "filesystem watchers missed events reconciliation",
            "deterministic fixtures reproducible failures",
            "prevent a previously fixed bug",
            "source bytes change cache",
        ],
    ),
]


def pdf(path: Path, pages: list[str]) -> None:
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        escaped = [
            line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            for line in textwrap.wrap(text, 80)
        ]
        stream = DecodedStreamObject()
        stream.set_data(
            (
                "BT /F1 11 Tf 50 740 Td 15 TL "
                + " ".join(f"({line}) Tj T*" for line in escaped)
                + " ET"
            ).encode("ascii")
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


def screenshot(path: Path, title: str, content: str) -> None:
    image = Image.new("RGB", (1400, 900), "#f7f6f3")
    draw = ImageDraw.Draw(image)
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = (
        ImageFont.truetype(str(font_path), 29)
        if font_path.exists()
        else ImageFont.load_default(size=29)
    )
    heading = (
        ImageFont.truetype(str(font_path), 46)
        if font_path.exists()
        else ImageFont.load_default(size=46)
    )
    draw.rectangle((70, 65, 1330, 835), fill="white", outline="#d5d8cf", width=2)
    draw.text((110, 105), title, fill="#2f342b", font=heading)
    draw.multiline_text(
        (110, 210), textwrap.fill(content, 76), fill="#41473b", font=font, spacing=19
    )
    image.save(path)


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--output", type=Path, default=Path("evaluation/corpus"))
    config = args.parse_args()
    corpus = config.output
    for folder in ("notes", "code", "documents", "screenshots"):
        (corpus / folder).mkdir(parents=True, exist_ok=True)
    queries, judgments, image_queries, image_judgments = [], [], [], []
    for index, (slug, title, content, phrases) in enumerate(TOPICS):
        relative = f"notes/{slug}.md"
        (corpus / relative).write_text(f"# {title}\n\n{content}\n", encoding="utf-8")
        split = "dev" if index < 6 else "test"
        for j, phrase in enumerate(phrases):
            qid = f"text-{slug}-{j + 1}"
            queries.append(
                {
                    "id": qid,
                    "query": phrase,
                    "category": "exact" if j in (0, 3) else "paraphrase",
                    "family": slug,
                    "split": split,
                }
            )
            judgments.append(
                {
                    "query_id": qid,
                    "path": relative,
                    "grade": 2,
                    "locator": {"line_start": 3, "line_end": 3},
                }
            )
        if slug == "dijkstra":
            for qid in [f"text-{slug}-2", f"text-{slug}-7"]:
                judgments.append(
                    {"query_id": qid, "path": "code/Dijkstra.java", "grade": 2}
                )
        if index < 3:
            image_path = f"screenshots/{slug}.png"
            screenshot(corpus / image_path, title, content)
            # Screenshots reproduce the full topic text and are relevant sources
            # for these unrestricted queries too; do not penalize valid OCR hits.
            for j in range(len(phrases)):
                judgments.append(
                    {"query_id": f"text-{slug}-{j + 1}", "path": image_path, "grade": 2}
                )
            for j, phrase in enumerate(
                phrases + [f"Screenshot showing {title.lower()}"]
            ):
                qid = f"image-{slug}-{j + 1}"
                image_queries.append(
                    {
                        "id": qid,
                        "query": phrase,
                        "category": "screenshot",
                        "family": slug,
                        "split": "dev",
                        "filters": {"modality": "image"},
                    }
                )
                image_judgments.append(
                    {"query_id": qid, "path": image_path, "grade": 2}
                )
    missing = [
        "medieval French poetry",
        "my invoice for a red bicycle",
        "a recipe for sourdough bread",
        "hotel booking in Iceland",
        "photos of coral reef fish",
        "mortgage amortization statement",
        "birthday party invitation",
        "a map of the moon",
        "travel itinerary for Peru",
        "the guitar chords to my song",
    ]
    for index, phrase in enumerate(missing):
        queries.append(
            {
                "id": f"missing-{index + 1}",
                "query": phrase,
                "category": "no_match",
                "family": f"missing-{index}",
                "split": "dev" if index < 6 else "test",
            }
        )
    (corpus / "code/Dijkstra.java").write_text(
        """import java.util.*;
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
""",
        encoding="utf-8",
    )
    (corpus / "code/search.py").write_text(
        '''def reciprocal_rank_fusion(rankings, constant=60):
    """Combine lexical and semantic retrieval by reciprocal ranks."""
    scores = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            scores[item] = scores.get(item, 0) + 1 / (constant + rank)
    return sorted(scores, key=scores.get, reverse=True)
''',
        encoding="utf-8",
    )
    pdf(corpus / "documents/operating_systems.pdf", [TOPICS[0][2], TOPICS[1][2]])
    pdf(corpus / "documents/cloud_architecture.pdf", [TOPICS[5][2]])
    for judgment in judgments[:]:
        if judgment["path"] in {
            "notes/semaphores.md",
            "notes/paging.md",
            "notes/load_balancing.md",
        }:
            page = 2 if judgment["path"] == "notes/paging.md" else 1
            path = (
                "documents/cloud_architecture.pdf"
                if "load_balancing" in judgment["path"]
                else "documents/operating_systems.pdf"
            )
            judgments.append(
                {
                    "query_id": judgment["query_id"],
                    "path": path,
                    "grade": 2,
                    "locator": {"page": page},
                }
            )
    destination = Path("evaluation")
    for name, records in (
        ("queries.jsonl", queries),
        ("judgments.jsonl", judgments),
        ("image_queries.jsonl", image_queries),
        ("image_judgments.jsonl", image_judgments),
    ):
        (destination / name).write_text(
            "\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8"
        )
    manifest = [
        {
            "path": path.relative_to(corpus).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(corpus.rglob("*"))
        if path.is_file()
    ]
    (destination / "corpus_manifest.json").write_text(
        json.dumps(
            {
                "license": "CC0-1.0",
                "description": "Authored synthetic study corpus; not a representative real-world benchmark",
                "files": manifest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"Created {len(manifest)} files, {len(queries)} text queries and {len(image_queries)} screenshot queries"
    )


if __name__ == "__main__":
    main()
