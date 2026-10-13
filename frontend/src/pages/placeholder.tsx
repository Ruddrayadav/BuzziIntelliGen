import { ArrowRight, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function PlaceholderPage({ icon: Icon, title, description, next }: { icon: LucideIcon; title: string; description: string; next?: { to: string; label: string } }) {
  return <Card className="mx-auto max-w-2xl p-8 text-center sm:p-12"><span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-blue-50 text-brand dark:bg-blue-950"><Icon size={26} /></span><h1 className="mt-6 text-2xl font-bold">{title}</h1><p className="mx-auto mt-3 max-w-lg leading-7 text-muted">{description}</p>{next && <Button asChild className="mt-7"><Link to={next.to}>{next.label} <ArrowRight size={17} /></Link></Button>}</Card>;
}
