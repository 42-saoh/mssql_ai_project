import Link from "next/link";
import {
  BatchProcedureTargetsInput,
  SingleProcedureTargetInput,
} from "@/components/procedure-search-combobox";
import type { MetadataProfile } from "@/lib/api/types";
import {
  outputDescriptions,
  outputLabels,
  requestedOutputOptions,
} from "@/lib/presentation";

export function RequestForm({
  defaultProfileId,
  profiles,
  action,
  batchAction,
}: Readonly<{
  defaultProfileId: string;
  profiles: MetadataProfile[];
  action: (formData: FormData) => Promise<void>;
  batchAction: (formData: FormData) => Promise<void>;
}>) {
  const effectiveDefaultProfileId = profiles.some((profile) => profile.id === "ppm")
    ? "ppm"
    : defaultProfileId;

  return (
    <>
      <form className="request-form" action={action}>
        <SingleProcedureTargetInput
          defaultProfileId={effectiveDefaultProfileId}
          profiles={profiles}
        />

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

        <WorkflowOptions />

        <div className="form-actions">
          <button type="submit">Submit request</button>
          <Link className="secondary-action" href="/metadata/design?intent=search">
            Search in design chat
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

        <BatchProcedureTargetsInput
          defaultProfileId={effectiveDefaultProfileId}
          profiles={profiles}
        />

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

        <WorkflowOptions />

        <div className="form-actions">
          <button type="submit">Submit batch</button>
        </div>
      </form>
    </>
  );
}

function WorkflowOptions() {
  return (
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
        <label>
          <span>Source context</span>
          <select name="sourceContextMode" defaultValue="RETRIEVED_SPANS">
            <option value="RETRIEVED_SPANS">retrieved spans</option>
            <option value="NONE">metadata only</option>
          </select>
        </label>
        <label>
          <span>Dependency analysis</span>
          <select name="sourceDependencyMode" defaultValue="CONFIRMED_PROCEDURES">
            <option value="CONFIRMED_PROCEDURES">confirmed procedures</option>
            <option value="NONE">root procedure only</option>
          </select>
        </label>
      </div>
    </fieldset>
  );
}
