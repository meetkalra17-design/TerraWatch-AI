import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { FloodZone } from "./FloodMap";
import { askRescueCopilot } from "./api";

type Props = {
  zones: FloodZone[];
};

type Message = {
  role: "assistant" | "operator";
  text: string;
};

const populationValue = (population: string) => Number(population.replace(/[^\d]/g, ""));

function buildResponse(question: string, zones: FloodZone[]) {
  const prompt = question.toLowerCase();
  const highest = zones[0];
  const totalPopulation = zones.reduce((sum, zone) => sum + populationValue(zone.population), 0);

  if (prompt.includes("safety") || prompt.includes("safe") || prompt.includes("do not")) {
    return "Safety first: confirm water depth, current, power-line exposure, bridge status, and route access with local responders before movement. Do not send vehicles or people into moving water. Use official emergency coordination, PPE, buddy checks, and an identified withdrawal route.";
  }
  if (prompt.includes("plan") || prompt.includes("next") || prompt.includes("deploy") || prompt.includes("rescue")) {
    return `Suggested first operational cycle: 1) verify ${highest.place} with field teams because it is ranked first at ${highest.depth} m estimated depth; 2) establish a safe staging point outside the inundation polygon; 3) request local confirmation of stranded people, access, power, and medical needs; 4) prioritize evacuation and medical support before property recovery; 5) review conditions after each field update. Current ranked-zone exposure is approximately ${totalPopulation.toLocaleString("en-IN")} people.`;
  }
  if (prompt.includes("why") || prompt.includes("priority") || prompt.includes("situation") || prompt.includes("status")) {
    return `Current map situation: ${zones.length} priority areas are ranked by estimated depth, severity, and affected population. ${highest.place} is first at ${highest.depth} m and ${highest.population}; the remaining priority areas are ${zones.slice(1).map((zone) => `${zone.place} (${zone.depth} m)`).join(", ")}. These are modeled map estimates, not verified field reports.`;
  }
  return "I can help with the current situation, priority ranking, a first-response plan, or safety checks. Try “What is the situation?”, “Make a rescue plan”, or “What should teams verify before deployment?”";
}

export default function RescueAssistant({ zones }: Props) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", text: "I’m your rescue planning copilot. I can turn the current map estimates into a cautious first-response plan." },
  ]);
  const suggestions = useMemo(() => ["What is the situation?", "Make a rescue plan", "What should teams verify?"], []);

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setMessages((current) => [...current, { role: "operator", text: trimmed }]);
    setInput("");
    setBusy(true);
    try {
      const response = await askRescueCopilot(trimmed, zones.map(({ name, place, severity, area, population, waterLevel, depth }) => ({ name, place, severity, area, population, waterLevel, depth })));
      setMessages((current) => [...current, { role: "assistant", text: response.answer }]);
    } catch {
      setMessages((current) => [...current, { role: "assistant", text: `${buildResponse(trimmed, zones)}\n\nLocal Ollama is unavailable, so this is the deterministic map-grounded fallback.` }]);
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(input);
  }

  return (
    <section className={`rescue-assistant ${open ? "open" : ""}`}>
      <button className="assistant-launcher" type="button" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="assistant-icon">✦</span>
        <span><strong>Rescue copilot</strong><small>Plan from current map intelligence</small></span>
        <b>{open ? "×" : "Ask"}</b>
      </button>
      {open && <div className="assistant-panel">
        <div className="assistant-heading"><div><p className="eyebrow">OPERATIONS ASSISTANT</p><h3>Rescue planning</h3></div><span className="assistant-status">MODELED · VERIFY</span></div>
        <div className="assistant-messages" aria-live="polite">
          {messages.map((message, index) => <div className={`assistant-message ${message.role}`} key={`${message.role}-${index}`}><span>{message.role === "assistant" ? "AI" : "You"}</span><p>{message.text}</p></div>)}
        </div>
        <div className="assistant-suggestions">{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => void ask(suggestion)} disabled={busy}>{suggestion}</button>)}</div>
        <form className="assistant-form" onSubmit={submit}><input aria-label="Ask rescue copilot" value={input} onChange={(event) => setInput(event.target.value)} placeholder={busy ? "Copilot is checking the local model…" : "Ask about this situation…"} disabled={busy} /><button type="submit" disabled={busy}>{busy ? "…" : "Send"}</button></form>
        <p className="assistant-disclaimer">Uses modeled map estimates. Confirm water, access, people, weather, and hazards with field teams and official emergency channels before dispatch.</p>
      </div>}
    </section>
  );
}
