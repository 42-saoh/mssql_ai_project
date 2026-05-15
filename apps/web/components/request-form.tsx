import Link from "next/link";
import type { MetadataProfile } from "@/lib/api/types";
import type { PilotManifestSummary, PilotMetadataObjectSample } from "@/lib/pilot-manifest";
import {
  outputDescriptions,
  outputLabels,
  requestedOutputOptions,
} from "@/lib/presentation";

export function RequestForm({
  defaultProfileId,
  profiles,
  pilotManifest,
  selectedSample,
  action,
  batchAction,
}: Readonly<{
  defaultProfileId: string;
  profiles: MetadataProfile[];
  pilotManifest: PilotManifestSummary;
  selectedSample?: PilotMetadataObjectSample;
  action: (formData: FormData) => Promise<void>;
  batchAction: (formData: FormData) => Promise<void>;
}>) {
  const effectiveProfileId = selectedSample ? "ppm" : defaultProfileId;
  const sampleName = selectedSample ? `${selectedSample.schema}.${selectedSample.name}` : "";

  return (
    <>
    <form className="request-form" action={action}>
      <section className="sample-strip" aria-label="PPM pilot sample requests">
        <div>
          <p className="eyebrow">PPM pilot samples</p>
          <h2>Sample request target</h2>
        </div>

        {pilotManifest.procedureSamples.length > 0 ? (
          <div className="sample-grid">
            {pilotManifest.procedureSamples.map((sample) => {
              const isSelected = sample.id === selectedSample?.id;

              return (
                <Link
                  className={`sample-option${isSelected ? " sample-option--selected" : ""}`}
                  href={`/requests/new?sample=${encodeURIComponent(sample.id)}`}
                  key={sample.id}
                >
                  <strong>{sample.id}</strong>
                  <span>{sample.complexity ?? "pilot"} procedure</span>
                  <small>
                    {sample.parameterCount ?? 0} params · {sample.dependencyCount ?? 0} dependency refs
                  </small>
                </Link>
              );
            })}
          </div>
        ) : (
          <div className="callout callout--warning">
            <strong>PPM samples hidden</strong>
            <p>
              The pilot manifest is {pilotManifest.selectionMode}; real object names are not
              rendered in this mode.
            </p>
          </div>
        )}

        {pilotManifest.activeBlockers.length > 0 ? (
          <div className="blocker-list">
            {pilotManifest.activeBlockers.map((blocker) => (
              <article className="blocker-row" key={blocker.code}>
                <strong>{blocker.code}</strong>
                <span>{blocker.message}</span>
              </article>
            ))}
          </div>
        ) : null}
      </section>

      <div className="form-grid">
        <label>
          <span>Metadata profile</span>
          <select name="dbProfileId" defaultValue={effectiveProfileId}>
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.id} - {profile.database}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Target type</span>
          <select name="targetType" defaultValue="PROCEDURE">
            <option value="PROCEDURE">Stored procedure</option>
          </select>
        </label>

        <label>
          <span>Schema</span>
          <input
            name="schema"
            defaultValue={selectedSample?.schema ?? "dbo"}
            placeholder="dbo"
            required
          />
        </label>

        <label>
          <span>Procedure name</span>
          <input
            name="name"
            defaultValue={selectedSample?.name ?? "usp_OrderRequest_Select"}
            placeholder={selectedSample?.name ?? "usp_OrderRequest_Select"}
            required
          />
        </label>
      </div>

      {selectedSample ? (
        <div className="callout">
          <strong>Selected manifest sample</strong>
          <p>
            {sampleName} uses dbProfileId <code>ppm</code>. It is metadata-only and remains
            review-required while dependency evidence is incomplete.
          </p>
        </div>
      ) : null}

      <fieldset>
        <legend>Requested outputs</legend>
        <div className="output-grid">
          {requestedOutputOptions.map((output) => (
            <label className="output-option" key={output}>
              <input
                type="checkbox"
                name="outputs"
                value={output}
                defaultChecked={
                  output === "SP_ANALYSIS_DOCUMENT" ||
                  output === "DEPENDENCY_REPORT" ||
                  output === "JAVA_MYBATIS_DRAFT"
                }
              />
              <span>
                <strong>{outputLabels[output]}</strong>
                <small>{outputDescriptions[output]}</small>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>Workflow options</legend>
        <div className="toggle-row">
          <label>
            <input type="checkbox" name="includeEvidenceRefs" defaultChecked />
            Include evidence refs
          </label>
          <label>
            <input type="checkbox" name="includeModernizationHints" defaultChecked />
            Include modernization hints
          </label>
          <label>
            <input type="checkbox" name="useLlmAnalysis" defaultChecked />
            Run high-quality LLM semantic analysis
          </label>
          <label>
            <input type="checkbox" name="useAiToolOrchestration" defaultChecked />
            Use bounded AI metadata tools
          </label>
          <label>
            <input type="checkbox" name="usePlatformToolOrchestration" defaultChecked />
            Use platform context tools
          </label>
          <label>
            <input type="checkbox" name="allowSpDefinitionToModel" defaultChecked />
            Allow transient SP definition in model input
          </label>
        </div>
        <div className="form-grid form-grid--compact">
          <label>
            <span>LLM profile</span>
            <select name="llmProfileId" defaultValue="openai_sp_semantic_analysis">
              <option value="openai_sp_semantic_analysis">semantic analysis - gpt-5.5</option>
              <option value="openai_fast_test">fast/test - gpt-5-nano</option>
            </select>
          </label>
        </div>
      </fieldset>

      <div className="form-actions">
        <button type="submit">Submit request</button>
        <Link className="secondary-action" href="/metadata/search">
          Search metadata
        </Link>
      </div>
    </form>
    <form className="request-form request-form--batch" action={batchAction}>
      <section className="sample-strip" aria-label="Batch stored procedure requests">
        <div>
          <p className="eyebrow">Batch mode</p>
          <h2>Stored procedure batch</h2>
        </div>
        <div className="callout">
          <strong>Bounded batch intake</strong>
          <p>
            Enter one <code>schema.name</code> PROCEDURE target per line. Duplicate targets are
            skipped and each accepted target creates a normal workflow job.
          </p>
        </div>
      </section>

      <div className="form-grid">
        <label>
          <span>Metadata profile</span>
          <select name="dbProfileId" defaultValue={effectiveProfileId}>
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.id} - {profile.database}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field--wide">
          <span>Procedure targets</span>
          <textarea
            name="batchTargets"
            defaultValue={sampleName ? `${sampleName}\n${sampleName}` : "dbo.usp_OrderRequest_Select"}
            rows={5}
            required
          />
        </label>
      </div>

      <fieldset>
        <legend>Requested outputs</legend>
        <div className="output-grid">
          {requestedOutputOptions.map((output) => (
            <label className="output-option" key={output}>
              <input
                type="checkbox"
                name="outputs"
                value={output}
                defaultChecked={
                  output === "SP_ANALYSIS_DOCUMENT" ||
                  output === "DEPENDENCY_REPORT" ||
                  output === "JAVA_MYBATIS_DRAFT"
                }
              />
              <span>
                <strong>{outputLabels[output]}</strong>
                <small>{outputDescriptions[output]}</small>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>Workflow options</legend>
        <div className="toggle-row">
          <label>
            <input type="checkbox" name="includeEvidenceRefs" defaultChecked />
            Include evidence refs
          </label>
          <label>
            <input type="checkbox" name="includeModernizationHints" defaultChecked />
            Include modernization hints
          </label>
          <label>
            <input type="checkbox" name="useLlmAnalysis" defaultChecked />
            Run high-quality LLM semantic analysis
          </label>
          <label>
            <input type="checkbox" name="useAiToolOrchestration" defaultChecked />
            Use bounded AI metadata tools
          </label>
          <label>
            <input type="checkbox" name="usePlatformToolOrchestration" defaultChecked />
            Use platform context tools
          </label>
          <label>
            <input type="checkbox" name="allowSpDefinitionToModel" defaultChecked />
            Allow transient SP definition in model input
          </label>
        </div>
        <div className="form-grid form-grid--compact">
          <label>
            <span>LLM profile</span>
            <select name="llmProfileId" defaultValue="openai_sp_semantic_analysis">
              <option value="openai_sp_semantic_analysis">semantic analysis - gpt-5.5</option>
              <option value="openai_fast_test">fast/test - gpt-5-nano</option>
            </select>
          </label>
        </div>
      </fieldset>

      <div className="form-actions">
        <button type="submit">Submit batch</button>
      </div>
    </form>
    </>
  );
}
