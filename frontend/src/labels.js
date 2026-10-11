export const labelFor = (category) =>
  category
    ? category.charAt(0).toUpperCase() + category.slice(1).replace(/_/g, " ")
    : "";

export function holder(c) {
  if (c.fu_level === 1) return `Head of ${c.department}`;
  if (c.fu_level >= 2) return "Commissioner's Office";
  return c.desk;
}

export function followUpText(c) {
  if (c.status === "duplicate") return `Duplicate of ${c.duplicate_of}`;
  if (c.status === "needs_details") return "Needs more details";
  if (c.fu_status === "closed" || c.fu_status === "resolved") return "Closed";
  if (c.fu_status === "critical") return "Critical: overdue at the top level";
  return c.fu_level > 0 ? `Escalated to ${holder(c)}` : `With ${holder(c)}`;
}

export function timeAgo(iso) {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}