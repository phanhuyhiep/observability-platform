# Phase 3 – Correlation Engine & Incident Intelligence

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Core Features](#core-features)
  - [1. Temporal Correlator](#1-temporal-correlator)
  - [2. Service Dependency Graph](#2-service-dependency-graph)
  - [3. Topology Correlator](#3-topology-correlator)
  - [4. Deployment Correlator](#4-deployment-correlator)
  - [5. Incident Engine](#5-incident-engine)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Deployment Guide](#deployment-guide)

---

## Overview

The **Correlation Engine** aggregates raw, isolated anomaly events produced by Phase 2 (Detection Service), correlates them using time-window sliding algorithms and topology graphs, and generates consolidated **Incidents** to eliminate alert fatigue.

```
Anomaly Events (Phase 2)
          │
          ▼
┌─────────────────────────────────────────────────────────┐
│                 Correlation Engine                      │
│                                                         │
│  1. Temporal Correlator   (Sliding Window Grouping)     │
│  2. Topology Correlator   (Dependency Graph & Root ID)  │
│  3. Deployment Correlator (Rollout Proximity Matching)  │
│  4. Incident Engine       (Grouping, Merge, Suppress)   │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
                  Consolidated Incidents
                   (INC-1001, INC-1002)
```

---

## Core Features

### 1. Temporal Correlator
- **Sliding Window:** Groups anomalies occurring within configurable intervals (default: 5 minutes).
- **Dynamic Window Extension:** Extends the window automatically (up to 15 minutes) if cascading anomalies keep occurring.
- **Inactivity Timeout:** Closes groups that have seen no new events for 10 minutes.

### 2. Service Dependency Graph
- In-memory `NetworkX` directed graph synchronized with PostgreSQL (`service_graph_nodes`, `service_graph_edges`).
- Automatically extracts caller ➔ callee relationships from **OpenTelemetry traces (Tempo)**.
- Pre-seeded with microservices-demo topology.
- Supports multi-hop upstream and downstream dependency queries.

### 3. Topology Correlator
- Identifies cascade propagation paths across connected services (e.g. `postgresql ➔ paymentservice ➔ checkoutservice`).
- Computes **Root Entity Candidate** using timestamp ordering and topological depth.
- Calculates **Topology Confidence** score (up to 95%).

### 4. Deployment Correlator
- Listens to CI/CD and Kubernetes rollout webhooks.
- Correlates anomalies occurring within 30 minutes after deployment.
- Attaches rollout version context and computes decaying confidence score.

### 5. Incident Engine
- **Auto-create:** Triggers an Incident when a group reaches $\ge 2$ anomalies or contains a `critical` severity event.
- **Auto-Title:** Generates readable, human-friendly titles:
  - `"[paymentservice] performance degradation after deployment v2.1.0"`
  - `"[postgresql] failure causing cascade to checkoutservice, paymentservice"`
- **Deduplication & Merge:** Merges overlapping incidents sharing entities or time windows.
- **Suppression:** Suppresses duplicate incidents when an active incident for the root cause already exists.

---

## API Reference

### Topology & Graph
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/topology/services` | Retrieve full service graph (nodes & edges) |
| `GET` | `/api/v1/topology/services/{id}` | Node detail and connected edges |
| `GET` | `/api/v1/topology/services/{id}/upstream` | Upstream callers (services depending on `{id}`) |
| `GET` | `/api/v1/topology/services/{id}/downstream` | Downstream callees (services that `{id}` depends on) |
| `POST` | `/api/v1/topology/edges` | Declare a manual dependency edge |
| `DELETE`| `/api/v1/topology/edges` | Remove a dependency edge |

### Correlation Groups
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/correlations` | List correlation groups (filter by `status`) |
| `GET` | `/api/v1/correlations/{id}` | Get group detail with its anomalies |
| `POST`| `/api/v1/correlations/evaluate` | Trigger on-demand correlation cycle |

### Incidents
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/incidents` | List incidents (filter by `status`, `severity`, `entity_id`) |
| `GET` | `/api/v1/incidents/{id}` | Get incident detail, root cause, and timeline |
| `PATCH`| `/api/v1/incidents/{id}` | Update status (`ACKNOWLEDGED`, `RESOLVED`, `CLOSED`) |

### Deployment Events
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/deployments` | Ingest deployment webhook from CI/CD |
| `GET` | `/api/v1/deployments` | List recent deployments |

---

## Testing

Run the automated unit test suite:

```bash
cd correlation
pytest tests/ -v
```

---

## Deployment Guide (Kubernetes)

1. Apply database migration:
   ```bash
   kubectl exec -i deployment/detection-postgres -n observability -- \
     psql -U detection -d detection_db < migrations/002_create_correlation_tables.sql
   ```

2. Build and deploy:
   ```bash
   eval $(minikube docker-env)
   docker build -t correlation-service:latest .
   kubectl apply -f k8s/correlation-deployment.yaml
   ```

3. Verify:
   ```bash
   kubectl get pods -n observability | grep correlation
   curl http://localhost:8081/health
   ```
