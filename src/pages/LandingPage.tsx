import { motion } from "framer-motion";
import { Leaf, ArrowRight, Shield, Zap, BarChart3 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { LayoutTextFlip } from "@/components/ui/layout-text-flip";
import { RotatingMicrocopy } from "@/components/ui/rotating-microcopy";
import { useAuth } from "@/hooks/use-auth";
import heroBg from "@/assets/hero-bg.jpg";

const features = [
  {
    icon: Zap,
    title: "Instant Detection",
    description: "Upload a photo and get disease diagnosis in seconds using advanced AI.",
  },
  {
    icon: Shield,
    title: "Treatment Suggestions",
    description: "Receive actionable treatment recommendations for identified diseases.",
  },
  {
    icon: BarChart3,
    title: "Track History",
    description: "Keep a detailed log of all past analyses for your crops.",
  },
];

const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.15 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: "easeOut" as const } },
};

export default function LandingPage() {
  const navigate = useNavigate();
  const { user, isLoading } = useAuth();

  const handleStartDetection = () => {
    navigate(user ? "/detect" : "/login");
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Hero */}
      <section className="relative flex-1 flex items-center justify-center px-6 py-24 overflow-hidden">
        {/* Background blobs */}
        {/* Background image */}
        <img
          src={heroBg}
          alt=""
          className="absolute inset-0 w-full h-full object-cover opacity-15 dark:opacity-10"
          width={1920}
          height={1080}
        />
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-40 -right-40 w-[500px] h-[500px] rounded-full gradient-hero opacity-20 blur-3xl" />
          <div className="absolute -bottom-40 -left-40 w-[400px] h-[400px] rounded-full gradient-accent opacity-15 blur-3xl" />
        </div>

        <motion.div
          className="relative z-10 max-w-3xl mx-auto text-center"
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          <motion.div variants={itemVariants} className="flex items-center justify-center gap-2 mb-6">
            <span className="glass-card px-4 py-2 rounded-full text-sm font-medium text-muted-foreground flex items-center gap-2 border border-primary/15 shadow-sm transition-all duration-300 hover:border-primary/40 hover:bg-primary/10 hover:text-foreground">
              <Leaf className="w-4 h-4 text-primary shrink-0" />
              <RotatingMicrocopy
                className="text-sm font-semibold text-foreground/90"
                intervalMs={3200}
                phrases={[
                  "AI-Powered Crop Analysis",
                  "Smarter field decisions",
                  "Real-time disease signals",
                  "From photo to action",
                ]}
              />
            </span>
          </motion.div>

          <motion.h1
            variants={itemVariants}
            className="text-4xl sm:text-5xl md:text-6xl font-display font-bold tracking-tight mb-6 text-center px-2"
          >
            <LayoutTextFlip
              text="AI Crop Disease"
              words={[
                "Detector 🌱",
                "Analyzer 🔬",
                "Scanner 🌾",
                "Protector 🛡️",
                "Forecaster 📈",
                "Watchdog 🔔",
              ]}
              duration={2400}
            />
          </motion.h1>

          <motion.p
            variants={itemVariants}
            className="text-lg sm:text-xl text-muted-foreground max-w-xl mx-auto mb-10 leading-relaxed"
          >
            <span className="text-foreground/90 font-medium">Upload a photo</span> and let our AI{" "}
            <RotatingMicrocopy
              className="text-primary font-semibold"
              intervalMs={2600}
              phrases={[
                "spot diseases early",
                "gauge severity fast",
                "suggest next steps",
                "track risk over time",
              ]}
            />{" "}
            — all in one guided flow.
          </motion.p>

          <motion.div variants={itemVariants}>
            <Button
              size="lg"
              className="gradient-hero text-primary-foreground font-semibold text-lg px-8 py-6 rounded-xl shadow-lg hover:opacity-90 transition-opacity animate-pulse-glow"
              onClick={handleStartDetection}
              disabled={isLoading}
            >
              {isLoading ? "Checking session..." : user ? "Start Detection" : "Login to Start Detection"}
              <ArrowRight className="ml-2 w-5 h-5" />
            </Button>
          </motion.div>
        </motion.div>
      </section>

      {/* Features */}
      <section className="px-6 pb-24">
        <motion.div
          className="max-w-4xl mx-auto grid md:grid-cols-3 gap-6"
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.3 }}
        >
          {features.map((f) => (
            <motion.div
              key={f.title}
              variants={itemVariants}
              whileHover={{ y: -4, transition: { duration: 0.25 } }}
              className="glass-card-elevated rounded-2xl p-6 border border-transparent transition-all duration-300 hover:scale-[1.02] hover:border-primary/35 hover:bg-primary/[0.06] hover:shadow-lg hover:shadow-primary/10"
            >
              <div className="w-12 h-12 rounded-xl gradient-hero flex items-center justify-center mb-4">
                <f.icon className="w-6 h-6 text-primary-foreground" />
              </div>
              <h3 className="font-display font-semibold text-lg mb-2">{f.title}</h3>
              <p className="text-muted-foreground text-sm leading-relaxed">{f.description}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>
    </div>
  );
}
