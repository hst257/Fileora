# Semantic search engineering

Semantic search converts queries and passages into dense embeddings. Normalized vectors can be ranked by cosine similarity using an inner product. BM25 ranks lexical matches using term frequency and inverse document frequency. Reciprocal rank fusion combines ranked candidate lists without adding incompatible raw scores. Metadata filters restrict eligible documents before retrieval. A cross encoder reranks a small candidate set using query and passage pairs.
