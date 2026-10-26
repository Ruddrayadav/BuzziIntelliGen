import { AlertCircle, BarChart3, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export function PageLoading() {
  return (
    <div className="grid min-h-64 place-items-center text-muted">
      <span className="inline-flex items-center gap-2">
        <LoaderCircle className="animate-spin" size={19} /> Loading your business data…
      </span>
    </div>
  );
}

export function PanelLoading() {
  return (
    <Card className="grid min-h-52 place-items-center p-6 text-muted">
      <span className="inline-flex items-center gap-2">
        <LoaderCircle className="animate-spin" size={19} /> Looking at your data…
      </span>
    </Card>
  );
}

export function PageError({ error, retry }: { error: Error; retry?: () => void }) {
  const message = error instanceof ApiError ? error.message : "We could not load this information.";
  return (
    <Card className="mx-auto mt-7 max-w-xl p-6 text-center">
      <AlertCircle className="mx-auto text-rose-600" />
      <h2 className="mt-3 font-bold">We could not load this page</h2>
      <p className="mt-2 text-sm text-muted">{message}</p>
      {retry && (
        <Button className="mt-5" variant="outline" onClick={retry}>
          Try again
        </Button>
      )}
    </Card>
  );
}

export function EmptyDashboard() {
  return (
    <Card className="mx-auto mt-7 max-w-2xl p-8 text-center">
      <BarChart3 className="mx-auto text-brand" size={30} />
      <h2 className="mt-4 text-xl font-bold">Your dashboard will appear here.</h2>
      <p className="mt-2 text-muted">Upload a sales or expense file to start seeing your business information.</p>
      <Button className="mt-6" asChild>
        <a href="/upload">Upload files</a>
      </Button>
    </Card>
  );
}

export function NoData({ text }: { text: string }) {
  return <Card className="p-8 text-center text-muted">{text}</Card>;
}

export function Severity({ severity }: { severity: "critical" | "warning" | "info" }) {
  const styles = {
    critical: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
    warning: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
    info: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
  };
  return (
    <span className={cn("rounded-full px-3 py-0.5 text-xs font-bold capitalize", styles[severity])}>
      {severity}
    </span>
  );
}
