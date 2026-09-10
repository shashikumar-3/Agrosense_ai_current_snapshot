import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import { Leaf } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();

  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full">
        <AppSidebar />
        <div className="flex-1 flex flex-col">
          <header className="h-14 flex items-center border-b border-border px-4 gap-3">
            <SidebarTrigger />
            <div className="flex items-center gap-2 flex-1">
              <Leaf className="w-5 h-5 text-primary" />
              <span className="font-display font-semibold text-sm">AgroSense AI</span>
            </div>
            {user && (
              <span className="text-xs text-muted-foreground hidden sm:block">
                Hi, {user.name || user.email} 👋
              </span>
            )}
          </header>
          <main className="flex-1 overflow-y-auto gradient-surface">{children}</main>
        </div>
      </div>
    </SidebarProvider>
  );
}
