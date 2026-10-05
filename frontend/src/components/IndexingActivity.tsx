import { CheckCircle, Clock, Spinner, X } from "@phosphor-icons/react";
import { useState } from "react";
import type { LibraryState } from "../hooks/useLibrary";

export function IndexingActivity({ library }: { library: LibraryState }) {
  const [expanded, setExpanded] = useState(false);
  const {
    jobs,
    indexing,
    jobDetail,
    setJobDetail,
    health,
    inspectJob,
    cancelJob,
  } = library;
  return (
    <section className="jobs-section">
      <div className="section-heading">
        <h2>Indexing activity</h2>
        <span className="small muted">
          {indexing
            ? "Running in the background"
            : jobs.length
              ? "Up to date with the last scan"
              : "No scans yet"}
        </span>
      </div>
      {jobs.length ? (
        jobs.slice(0, expanded ? jobs.length : 3).map((job) => (
          <div className="job-row" key={job.id}>
            <span>
              {["queued", "running"].includes(job.state) ? (
                <Spinner className="spin" size={21} />
              ) : job.state === "completed" ? (
                <CheckCircle size={21} weight="duotone" />
              ) : (
                <Clock size={21} />
              )}
            </span>
            <button className="job-info" onClick={() => void inspectJob(job)}>
              <strong>
                {job.state === "completed"
                  ? "Library scan completed"
                  : `Library scan ${job.state}`}
              </strong>
              <span>
                {job.indexed} indexed · {job.skipped} skipped · {job.deleted}{" "}
                removed · {job.failed} failed
              </span>
            </button>
            {["queued", "running"].includes(job.state) && (
              <button
                className="text-button"
                onClick={() => void cancelJob(job)}
              >
                Cancel
              </button>
            )}
            <time>
              {new Date(
                job.created_at.replace(" ", "T") + "Z",
              ).toLocaleString()}
            </time>
          </div>
        ))
      ) : (
        <p className="muted">Add a folder and run your first scan.</p>
      )}
      {jobs.length > 3 && (
        <button
          className="text-button"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded
            ? "Show fewer scans"
            : `Show ${jobs.length - 3} earlier scans`}
        </button>
      )}
      {jobDetail && (
        <div className="job-detail">
          <div className="section-heading">
            <strong>Scan details</strong>
            <button
              aria-label="Close scan details"
              onClick={() => setJobDetail(undefined)}
            >
              <X size={18} />
            </button>
          </div>
          {!health?.media_enabled && (
            <p>
              Audio and video files are skipped because transcription is off.
            </p>
          )}
          {jobDetail.errors?.length ? (
            jobDetail.errors.map((item, index) => (
              <p key={index}>
                <strong>{item.relative_path || "Folder scan"}</strong>
                <br />
                {item.code}: {item.message}
              </p>
            ))
          ) : (
            <p>No errors recorded for this scan.</p>
          )}
        </div>
      )}
    </section>
  );
}
