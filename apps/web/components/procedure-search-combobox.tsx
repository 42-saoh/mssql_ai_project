"use client";

import { useEffect, useId, useMemo, useState } from "react";
import type { MetadataProfile } from "@/lib/api/types";

interface ProcedureSuggestion {
  schema: string;
  name: string;
  targetKey?: string | null;
  sourceDatabase?: string;
  reviewRequired?: boolean;
  caveats?: string[];
}

interface ProcedureSearchResponse {
  suggestions?: ProcedureSuggestion[];
  code?: string;
  message?: string;
}

interface ProcedureSearchComboboxProps {
  dbProfileId: string;
  label: string;
  placeholder?: string;
  onTargetChange: (target: { schema: string; name: string; display: string }) => void;
}

export function SingleProcedureTargetInput({
  defaultProfileId,
  profiles,
}: Readonly<{
  defaultProfileId: string;
  profiles: MetadataProfile[];
}>) {
  const [dbProfileId, setDbProfileId] = useState(defaultProfileId);
  const [target, setTarget] = useState({
    schema: "dbo",
    name: "",
    display: "",
  });

  return (
    <div className="form-grid">
      <label>
        <span>Metadata profile</span>
        <select
          name="dbProfileId"
          value={dbProfileId}
          onChange={(event) => setDbProfileId(event.target.value)}
        >
          {profiles.map((profile) => (
            <option key={profile.id} value={profile.id}>
              {profile.id} - {profile.database}
            </option>
          ))}
        </select>
      </label>
      <input name="targetType" readOnly type="hidden" value="PROCEDURE" />
      <input name="schema" readOnly type="hidden" value={target.schema} />
      <input name="name" readOnly type="hidden" value={target.name} />
      <ProcedureSearchCombobox
        dbProfileId={dbProfileId}
        label="Procedure"
        onTargetChange={setTarget}
        placeholder="Search procedure name"
      />
    </div>
  );
}

export function BatchProcedureTargetsInput({
  defaultProfileId,
  profiles,
}: Readonly<{
  defaultProfileId: string;
  profiles: MetadataProfile[];
}>) {
  const [dbProfileId, setDbProfileId] = useState(defaultProfileId);
  const [target, setTarget] = useState({ schema: "dbo", name: "", display: "" });
  const [batchTargets, setBatchTargets] = useState("");
  const [message, setMessage] = useState("Search and add PROCEDURE targets one at a time.");

  function addTarget() {
    const parsed = parseProcedureInput(target.display);
    if (!parsed.name) {
      setMessage("Choose or type a procedure before adding it.");
      return;
    }
    const nextTarget = `${parsed.schema}.${parsed.name}`;
    const currentTargets = batchTargets
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const exists = currentTargets.some(
      (line) => line.toLowerCase() === nextTarget.toLowerCase(),
    );
    if (exists) {
      setMessage(`${nextTarget} is already in the batch.`);
      return;
    }
    setBatchTargets([...currentTargets, nextTarget].join("\n"));
    setMessage(`Added ${nextTarget}.`);
  }

  return (
    <div className="form-grid">
      <label>
        <span>Metadata profile</span>
        <select
          name="dbProfileId"
          value={dbProfileId}
          onChange={(event) => setDbProfileId(event.target.value)}
        >
          {profiles.map((profile) => (
            <option key={profile.id} value={profile.id}>
              {profile.id} - {profile.database}
            </option>
          ))}
        </select>
      </label>
      <div className="procedure-batch-picker">
        <ProcedureSearchCombobox
          dbProfileId={dbProfileId}
          label="Find procedure"
          onTargetChange={setTarget}
          placeholder="Search procedure to add"
        />
        <button type="button" onClick={addTarget}>
          Add to batch
        </button>
        <p className="field-hint" aria-live="polite">
          {message}
        </p>
      </div>
      <label className="form-field--wide">
        <span>Procedure targets</span>
        <textarea
          name="batchTargets"
          value={batchTargets}
          onChange={(event) => setBatchTargets(event.target.value)}
          rows={5}
          required
        />
      </label>
    </div>
  );
}

function ProcedureSearchCombobox({
  dbProfileId,
  label,
  onTargetChange,
  placeholder = "Search procedure",
}: Readonly<ProcedureSearchComboboxProps>) {
  const inputId = useId();
  const listboxId = useId();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<ProcedureSuggestion[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState("Type to search procedures.");
  const normalizedQuery = query.trim();

  useEffect(() => {
    setSuggestions([]);
    setStatus("Type to search procedures.");
  }, [dbProfileId]);

  useEffect(() => {
    if (normalizedQuery.length === 0) {
      setSuggestions([]);
      setIsLoading(false);
      setStatus("Type to search procedures.");
      return undefined;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setIsLoading(true);
      setStatus("Searching procedures...");
      try {
        const params = new URLSearchParams({
          dbProfileId,
          query: normalizedQuery,
          limit: "100",
        });
        const response = await fetch(`/api/metadata/procedure-search?${params.toString()}`, {
          signal: controller.signal,
        });
        const payload = (await response.json()) as ProcedureSearchResponse;
        if (!response.ok) {
          throw new Error(payload.message ?? `HTTP ${response.status}`);
        }
        const nextSuggestions = payload.suggestions ?? [];
        setSuggestions(nextSuggestions);
        setStatus(
          nextSuggestions.length > 0
            ? `${nextSuggestions.length} procedure candidates`
            : "No procedures found.",
        );
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setSuggestions([]);
        setStatus(error instanceof Error ? error.message : "Procedure search failed.");
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    }, 250);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [dbProfileId, normalizedQuery]);

  const activeTarget = useMemo(() => parseProcedureInput(query), [query]);

  function updateQuery(nextQuery: string) {
    setQuery(nextQuery);
    const parsed = parseProcedureInput(nextQuery);
    onTargetChange({ ...parsed, display: nextQuery });
  }

  function chooseSuggestion(suggestion: ProcedureSuggestion) {
    const display = `${suggestion.schema}.${suggestion.name}`;
    updateQuery(display);
    setSuggestions([]);
    setStatus(`Selected ${display}.`);
  }

  return (
    <div className="procedure-combobox">
      <label htmlFor={inputId}>
        <span>{label}</span>
        <input
          aria-autocomplete="list"
          aria-controls={listboxId}
          aria-expanded={suggestions.length > 0}
          autoComplete="off"
          id={inputId}
          onChange={(event) => updateQuery(event.target.value)}
          placeholder={placeholder}
          role="combobox"
          type="search"
          value={query}
          required
        />
      </label>
      <p className="field-hint" aria-live="polite">
        {isLoading ? "Searching procedures..." : status}
      </p>
      <code
        aria-hidden={!activeTarget.name}
        className={activeTarget.name ? "field-code" : "field-code field-code--empty"}
      >
        {activeTarget.name ? `${activeTarget.schema}.${activeTarget.name}` : "dbo.procedure"}
      </code>
      {suggestions.length > 0 ? (
        <div className="procedure-suggestions" id={listboxId} role="listbox">
          {suggestions.map((suggestion) => {
            const display = `${suggestion.schema}.${suggestion.name}`;
            return (
              <button
                aria-selected={query.toLowerCase() === display.toLowerCase()}
                className="procedure-suggestion"
                key={`${suggestion.schema}.${suggestion.name}.${suggestion.targetKey ?? ""}`}
                onClick={() => chooseSuggestion(suggestion)}
                role="option"
                type="button"
              >
                <strong>{display}</strong>
                {suggestion.targetKey ? <code>{suggestion.targetKey}</code> : null}
                <small>
                  {suggestion.sourceDatabase ?? dbProfileId}
                  {suggestion.reviewRequired ? " - Evidence caveat" : ""}
                </small>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function parseProcedureInput(value: string): { schema: string; name: string } {
  const normalized = value.trim();
  if (!normalized) {
    return { schema: "dbo", name: "" };
  }
  const [schema, ...nameParts] = normalized.split(".");
  if (nameParts.length === 0) {
    return { schema: "dbo", name: schema.trim() };
  }
  return {
    schema: schema.trim() || "dbo",
    name: nameParts.join(".").trim(),
  };
}
