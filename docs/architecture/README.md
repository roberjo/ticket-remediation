# Solution Architecture Documentation

This is the architecture documentation for **ticket-remediation** — an automation system that
turns ServiceNow application-vulnerability findings into merged code and infrastructure fixes.
It follows the [arc42](https://arc42.org/) structure (a widely used template for software
architecture documentation) combined with [C4 model](https://c4model.com/) diagrams for the
structural views, plus UML sequence/state/class diagrams for behavior and data. All diagrams are
[Mermaid](https://mermaid.js.org/), rendered natively by GitHub — no external tooling needed to
view them.

| # | Section | Covers |
|---|---|---|
| 1 | [Introduction & Goals](01-introduction-and-context.md) | Purpose, quality goals, stakeholders, constraints, system context (C4 Context diagram) |
| 2 | [Solution Strategy](02-solution-strategy.md) | The key architectural decisions and the reasoning behind each |
| 3 | [Building Block View](03-building-blocks.md) | C4 Container/Component diagrams, module structure, UML class diagrams for the connector interfaces |
| 4 | [Runtime View](04-runtime-view.md) | UML sequence diagrams for the ingest flow, the remediate flow (happy path, idempotent skip, and failure), and notification fan-out |
| 5 | [Data & State Model](05-data-and-state-model.md) | Entity-relationship diagram, domain model class diagram, and the remediation-run state machine |
| 6 | [Use Cases](06-use-cases.md) | Actors, a use-case diagram, and full use-case descriptions |
| 7 | [Deployment View](07-deployment-view.md) | How the system actually runs, in both zero-budget/local-mock mode and a real cron-scheduled deployment |
| 8 | [Cross-Cutting Concerns, Risks & Glossary](08-cross-cutting-and-risks.md) | Security posture, testing strategy, error-handling philosophy, known limitations, and domain terminology |

## Reading order

If you're new to the project, read in order: sections 1 → 3 give you the "what and why", section
4 gives you the "how it behaves", sections 5–6 fill in data and user-facing detail, and 7–8 cover
running it for real and where the edges are. If you just need one diagram, the table above tells
you which file has it.

## Keeping this current

These documents describe the system as of the `remediate` pipeline supporting three target
domains — React frontend, Express backend, and Terraform infrastructure-as-code — routed through
the same generic, technology-agnostic LLM remediation step. If the architecture changes
meaningfully (a new connector type, a new trigger model, a new state machine transition), update
the relevant section here in the same change.
