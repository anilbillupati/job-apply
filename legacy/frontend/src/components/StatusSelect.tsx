import { JOB_STATUSES, type JobStatus } from "../types/job";

interface Props {
  value: JobStatus;
  onChange: (status: JobStatus) => void;
  disabled?: boolean;
}

export function StatusSelect({ value, onChange, disabled }: Props) {
  return (
    <select
      className={`status status-${value}`}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as JobStatus)}
    >
      {JOB_STATUSES.map((s) => (
        <option key={s} value={s}>
          {s}
        </option>
      ))}
    </select>
  );
}
