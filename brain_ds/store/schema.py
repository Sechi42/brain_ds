"""Schema DDL for SQLite graph store."""

DDL_SCRIPT = """
CREATE TABLE IF NOT EXISTS store_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graphs (
    id TEXT PRIMARY KEY,
    workspace_root TEXT NOT NULL,
    workspace_path TEXT NOT NULL,
    project TEXT NOT NULL,
    org TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    node_count INTEGER NOT NULL DEFAULT 0,
    edge_count INTEGER NOT NULL DEFAULT 0,
    imported_from TEXT,
    generated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    graph_id TEXT NOT NULL,
    id TEXT NOT NULL,
    label TEXT NOT NULL,
    type TEXT NOT NULL,
    supertype TEXT,
    details TEXT,
    card_sections TEXT,
    editable_fields TEXT,
    evidence_ids TEXT,
    layout_hint TEXT,
    parent_id TEXT,
    depth INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    modified_at TEXT NOT NULL,
    PRIMARY KEY (graph_id, id),
    FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS edges (
    graph_id TEXT NOT NULL,
    edge_id TEXT NOT NULL,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    label TEXT NOT NULL,
    weight REAL,
    reasons TEXT,
    evidence_ids TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (graph_id, edge_id),
    FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evidence (
    graph_id TEXT NOT NULL,
    id TEXT NOT NULL,
    type TEXT NOT NULL,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    provenance TEXT,
    timestamp TEXT,
    PRIMARY KEY (graph_id, id),
    FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS clusters (
    graph_id TEXT NOT NULL,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    parent_id TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (graph_id, id),
    FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cluster_members (
    graph_id TEXT NOT NULL,
    cluster_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    weight REAL,
    PRIMARY KEY (graph_id, cluster_id, node_id),
    FOREIGN KEY (graph_id, cluster_id) REFERENCES clusters(graph_id, id) ON DELETE CASCADE,
    FOREIGN KEY (graph_id, node_id) REFERENCES nodes(graph_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    graph_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK(target_type IN ('node', 'edge', 'evidence', 'cluster')),
    target_id TEXT NOT NULL,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    vector BLOB NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(graph_id, target_type, target_id, model),
    FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_graphs_project ON graphs(project);
CREATE INDEX IF NOT EXISTS idx_nodes_graph_type ON nodes(graph_id, type);
CREATE INDEX IF NOT EXISTS idx_nodes_graph_supertype ON nodes(graph_id, supertype);
CREATE INDEX IF NOT EXISTS idx_nodes_graph_parent ON nodes(graph_id, parent_id);
CREATE INDEX IF NOT EXISTS idx_edges_graph_source ON edges(graph_id, source);
CREATE INDEX IF NOT EXISTS idx_edges_graph_target ON edges(graph_id, target);
CREATE INDEX IF NOT EXISTS idx_evidence_graph_source ON evidence(graph_id, source);
CREATE INDEX IF NOT EXISTS idx_cluster_members_node ON cluster_members(graph_id, node_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_target ON embeddings(graph_id, target_type, target_id, model);
"""

TABLES = (
    "store_meta",
    "graphs",
    "nodes",
    "edges",
    "evidence",
    "clusters",
    "cluster_members",
    "embeddings",
)

INDICES = (
    "idx_graphs_project",
    "idx_nodes_graph_type",
    "idx_nodes_graph_supertype",
    "idx_nodes_graph_parent",
    "idx_edges_graph_source",
    "idx_edges_graph_target",
    "idx_evidence_graph_source",
    "idx_cluster_members_node",
    "idx_embeddings_target",
)
