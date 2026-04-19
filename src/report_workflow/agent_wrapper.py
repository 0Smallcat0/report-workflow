from report_workflow.run_workflow import prepare_workflow, validate_workflow, render_workflow
from report_workflow.errors import AgentWorkRequired, QAHardBlockError

def start_report_task(prompt: str, source_files: list[str], output_dir: str, report_family: str | None = None) -> dict:
    """
    Start the report generation workflow.
    This creates the initial task briefs for the agent to complete.
    """
    try:
        state = prepare_workflow(prompt, source_files, output_dir, report_family=report_family)
        if state.status == "awaiting_agent_artifacts":
            return {
                "status": "awaiting_agent_artifacts",
                "job_id": state.job_id,
                "message": f"Agent work required. Please read the task briefs located in ~/.hermes/workflow_runs/{state.job_id}/agent_tasks/",
            }
        return {"status": state.status, "job_id": state.job_id, "message": "Workflow completed successfully."}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

def submit_and_publish_report(job_id: str) -> dict:
    """
    Submit the agent-authored artifacts, run validation gates, and render the final DOCX.
    """
    try:
        state = validate_workflow(job_id)
        state = render_workflow(job_id)
        return {
            "status": state.status,
            "job_id": state.job_id,
            "final_docx_path": state.output.get("final_docx_path", ""),
            "message": "Report validation passed and DOCX successfully rendered!"
        }
    except AgentWorkRequired as e:
        return {
            "status": "validation_failed",
            "job_id": job_id,
            "message": "Missing agent artifacts. You must create all required JSON and MD files before submitting.",
            "missing_artifacts": e.missing_artifacts
        }
    except QAHardBlockError as e:
        return {
            "status": "validation_failed",
            "job_id": job_id,
            "message": "QA Gates Failed. You must revise your artifacts and submit again.",
            "error_details": str(e)
        }
    except Exception as e:
         return {"status": "failed", "error": str(e)}
