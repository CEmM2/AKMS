# Diagram recipes

## Module dependency (Mermaid)
```mermaid
graph TD
  A[package_a] --> B[package_b]
  A --> C[package_c]
  C --> D[external_lib]
```

## Dataflow diagram (Mermaid)
```mermaid
flowchart LR
  In[Input data] --> Pre[Preprocessing]
  Pre --> Core[Core compute]
  Core --> Post[Postprocessing]
  Post --> Out[Outputs]
```
## Lifecycle / state machine (Mermaid)
```mermaid
stateDiagram-v2
  [*] --> Init
  Init --> Ready
  Ready --> Running
  Running --> Ready
  Running --> Fault
  Fault --> SafeStop
  SafeStop --> [*]
```

## Data provenance graph (Mermaid)
```mermaid
flowchart TD
  Raw[Raw data] --> Clean[Cleaned]
  Clean --> Feat[Derived features]
  Feat --> Model[Model/Params]
  Model --> Pred[Predictions/Outputs]
```

## Class relationships (Mermaid)
```mermaid
classDiagram
  Base <|-- DerivedA
  Base <|-- DerivedB
  DerivedA --> Helper : uses
```

## Graphviz DOT (when Mermaid gets messy)

```dot
digraph G {
  rankdir=LR;
  A -> B;
  A -> C;
  C -> D;
}
```

### LaTeX/TikZ note

Prefer TikZ for small diagrams. For large dependency graphs:
- Generate DOT → PDF, then include with \includegraphics.

