import { ActivityFeed } from "@/features/activity/activity-feed";

export default function ActivityPage() {
  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-foreground text-2xl font-semibold">Recent activity</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          A record of what you have created, changed, archived and deleted.
        </p>
      </div>
      <ActivityFeed />
    </div>
  );
}
