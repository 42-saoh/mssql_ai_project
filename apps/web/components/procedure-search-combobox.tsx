"use client";

import { useMemo, useState } from "react";
import type { MetadataProfile } from "@/lib/api/types";

interface ProcedureTargetInputProps {
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
      <ProcedureTargetInput
        label="Procedure"
        onTargetChange={setTarget}
        placeholder="dbo.usp_ProcessOrder"
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
  const [message, setMessage] = useState("Type and add PROCEDURE targets one at a time.");

  function addTarget() {
    const parsed = parseProcedureInput(target.display);
    if (!parsed.name) {
      setMessage("Type a procedure before adding it.");
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
        <ProcedureTargetInput
          label="Procedure"
          onTargetChange={setTarget}
          placeholder="dbo.usp_ProcessOrder"
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

function ProcedureTargetInput({
  label,
  onTargetChange,
  placeholder = "dbo.procedure",
}: Readonly<ProcedureTargetInputProps>) {
  const [query, setQuery] = useState("");
  const activeTarget = useMemo(() => parseProcedureInput(query), [query]);

  function updateQuery(nextQuery: string) {
    setQuery(nextQuery);
    const parsed = parseProcedureInput(nextQuery);
    onTargetChange({ ...parsed, display: nextQuery });
  }

  return (
    <div className="procedure-combobox">
      <label>
        <span>{label}</span>
        <input
          autoComplete="off"
          onChange={(event) => updateQuery(event.target.value)}
          placeholder={placeholder}
          value={query}
          required
        />
      </label>
      <p className="field-hint">Use Metadata design chat to search before submitting.</p>
      <code
        aria-hidden={!activeTarget.name}
        className={activeTarget.name ? "field-code" : "field-code field-code--empty"}
      >
        {activeTarget.name ? `${activeTarget.schema}.${activeTarget.name}` : "dbo.procedure"}
      </code>
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
