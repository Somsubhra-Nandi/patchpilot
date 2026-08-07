import { Check } from "lucide-react";

const steps = [
  ["message_received", "Intake"],
  ["repository_inspected", "Repository analysis"],
  ["plan_generated", "Plan"],
  ["approval_received", "Approval"],
  ["changes_generated", "Implementation"],
  ["tests_run", "Validation & PR"],
];

const allStages = ["message_received", "issue_loaded", "repository_inspected", "files_identified", "plan_generated", "approval_requested", "approval_received", "branch_prepared", "changes_generated", "tests_run", "pull_request_created", "maintainers_notified"];

export function WorkflowProgress({ currentStage, status }: { currentStage: string; status: string }) {
  const currentIndex = allStages.indexOf(currentStage);
  return (
    <section className="panel workflow-panel" aria-label="Workflow progress">
      <div className="workflow-title"><h2>Execution path</h2><span>{currentStage.replaceAll("_", " ")}</span></div>
      <div className="workflow-steps">
        {steps.map(([stage, label], index) => {
          const stageIndex = allStages.indexOf(stage);
          const done = currentIndex > stageIndex || status === "completed";
          const nextStage = steps[index + 1]?.[0];
          const current = currentIndex >= stageIndex && (!nextStage || currentIndex < allStages.indexOf(nextStage));
          return <div className={`workflow-step ${done ? "done" : current ? "current" : ""}`} key={stage}><span className="workflow-node">{done && <Check size={11} />}</span><label>{label}</label></div>;
        })}
      </div>
    </section>
  );
}
