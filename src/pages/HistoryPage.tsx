import { useEffect } from "react";
import { motion } from "framer-motion";
import { Clock, Loader2, AlertCircle } from "lucide-react";
import { useHistory } from "@/hooks/use-api";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4 } },
};

export default function HistoryPage() {
  const { history, fetchHistory, clearHistory, isLoading, isClearing, error } = useHistory();
  const { toast } = useToast();

  useEffect(() => {
    fetchHistory().catch(() => {
      toast({
        title: "Error",
        description: "Could not load history. Make sure the backend is running.",
        variant: "destructive",
      });
    });
  }, [fetchHistory, toast]);

  const handleClearHistory = async () => {
    try {
      await clearHistory();
      toast({
        title: "History cleared",
        description: "All detection records have been removed.",
      });
    } catch {
      toast({
        title: "Clear failed",
        description: "Could not clear history right now.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-6 py-12">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4"
      >
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Detection History</h1>
          <p className="text-muted-foreground">Previous crop analyses and results.</p>
        </div>
        <Button
          variant="outline"
          onClick={() => void handleClearHistory()}
          disabled={isLoading || isClearing || history.length === 0}
          className="rounded-xl transition-colors duration-200 hover:bg-primary/15 hover:border-primary/70 hover:text-foreground dark:hover:bg-primary/20"
        >
          {isClearing ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Clearing...
            </>
          ) : (
            "Clear History"
          )}
        </Button>
      </motion.div>

      {isLoading && (
        <div className="flex items-center justify-center py-24">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        </div>
      )}

      {!isLoading && error && (
        <div className="glass-card rounded-2xl p-8 text-center">
          <AlertCircle className="w-12 h-12 mx-auto text-destructive mb-3" />
          <p className="font-semibold">Could not load history</p>
          <p className="text-sm text-muted-foreground mt-1">Ensure the backend is running at localhost:5000</p>
        </div>
      )}

      {!isLoading && !error && history.length === 0 && (
        <div className="glass-card rounded-2xl p-12 text-center">
          <Clock className="w-12 h-12 mx-auto text-muted-foreground mb-3" />
          <p className="font-semibold">No history yet</p>
          <p className="text-sm text-muted-foreground mt-1">Analyzed crops will appear here.</p>
        </div>
      )}

      {!isLoading && history.length > 0 && (
        <motion.div
          className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5"
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          {history.map((item) => {
            const isHealthy = item.disease.toLowerCase().includes("healthy");
            return (
              <motion.div
                key={item.id}
                variants={itemVariants}
                className={`glass-card-elevated rounded-2xl overflow-hidden border-l-4 transition-all duration-300 hover:-translate-y-0.5 hover:bg-primary/[0.04] hover:shadow-lg hover:ring-2 hover:ring-primary/35 ${
                  isHealthy ? "border-healthy" : "border-diseased"
                }`}
              >
                {item.image_url && (
                  <div className="h-36 overflow-hidden">
                    <img src={item.image_url} alt={item.disease} className="w-full h-full object-cover" />
                  </div>
                )}
                <div className="p-4 space-y-1">
                  <p className={`font-display font-semibold ${isHealthy ? "status-healthy" : "status-diseased"}`}>
                    {item.disease}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(item.date).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "short",
                      day: "numeric",
                    })}
                  </p>
                </div>
              </motion.div>
            );
          })}
        </motion.div>
      )}
    </div>
  );
}
