# Creating New Voice Agents with VaaniKit

VaaniKit is designed as an open-source starter kit for Indian-language voice agents. You can adapt it to any service or booking domain simply by providing a declarative configuration file and registering your tools.

---

## 1. Quickstart

To create a new agent, pick a starter template from `templates/` or create a new YAML file:

```bash
# Example: Create a restaurant reservation voice agent
cp templates/restaurant-reservation.yaml my-agent.yaml
```

Set the environment variable pointing to your configuration:

```bash
export AGENT_CONFIG_PATH="my-agent.yaml"
```

Then start the application:

```bash
make dev
```

---

## 2. Configuration Schema (`agent.yaml`)

Every agent configuration specifies:

* **`agent`**:
  * `name`: Identifier for the agent instance.
  * `language`: Primary language code (e.g. `ml-IN`, `hi-IN`, `ta-IN`, `en-IN`).
  * `greeting`: Opening spoken phrase when the call connects.
  * `persona`: System prompt / behavior definition.
  * `rules`: Ordered operational rules (e.g. confirmation requirements, privacy policies).
* **`model`**:
  * `provider`: Model adapter provider (`gnani` or fallback).
  * `stt`: Speech-to-text configuration (e.g. `prisma-v3.0`).
  * `tts`: Text-to-speech voice and language mapping.
  * `date_time_resolver`: Heuristic or LLM-backed date/time resolution.
* **`tools`**:
  * List of declared tool names, parameters schemas, and whether they are enabled.
  * **Strict security boundary:** Undeclared tools are rejected at runtime.

---

## 3. Pre-Built Starter Templates

VaaniKit ships with ready-to-run configurations in `templates/`:

1. **`templates/restaurant-reservation.yaml`**: Table booking line with party size, indoor/outdoor preferences, and date/time checking.
2. **`templates/diagnostic-lab.yaml`**: Home sample collection scheduling for diagnostic clinics, including fasting verification and morning slots.
3. **`templates/service-center.yaml`**: Appliance repair customer service assistant with technician scheduling.

---

## 4. Registering Custom Tools

To implement domain-specific tools:

1. Define a tool handler function in `app/tools/`:
   ```python
   async def handle_table_booking(arguments: dict[str, Any]) -> dict[str, Any]:
       # Business logic here
       return {"status": "reserved", "table_number": 12}
   ```
2. Declare the tool in your YAML file under `tools:`.
3. Register it with the tool registry:
   ```python
   registry.register("reserve_table", spec, handle_table_booking)
   ```
