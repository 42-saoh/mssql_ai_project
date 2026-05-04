import Link from "next/link";
import type { MetadataProfile } from "@/lib/api/types";
import {
  outputDescriptions,
  outputLabels,
  requestedOutputOptions,
} from "@/lib/presentation";

export function RequestForm({
  defaultProfileId,
  profiles,
}: Readonly<{
  defaultProfileId: string;
  profiles: MetadataProfile[];
}>) {
  return (
    <form className="request-form" action="/jobs/job_demo_draft" method="get">
      <div className="form-grid">
        <label>
          <span>Metadata profile</span>
          <select name="dbProfileId" defaultValue={defaultProfileId}>
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
          <input name="schema" defaultValue="dbo" placeholder="dbo" />
        </label>

        <label>
          <span>Procedure name</span>
          <input
            name="name"
            defaultValue="usp_OrderRequest_Select"
            placeholder="usp_OrderRequest_Select"
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
        </div>
      </fieldset>

      <div className="form-actions">
        <button type="submit">Open mock draft job</button>
        <Link className="secondary-action" href="/jobs/job_demo_review_pending">
          View review queue example
        </Link>
      </div>
    </form>
  );
}
