import { useState } from "react";
import { motion } from "framer-motion";
import { useNavigate, Link } from "react-router-dom";
import { Mail, Lock, User, Loader2, Leaf } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/use-auth";
import { useToast } from "@/hooks/use-toast";
import { AuthFieldErrors, validateSignup } from "@/lib/auth-validation";

const spring = { type: "spring" as const, stiffness: 300, damping: 24 };

export default function SignupPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<AuthFieldErrors>({});
  const { signup, isLoading } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const validationErrors = validateSignup(name, email, password);
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length) return;
    try {
      await signup(email.trim(), password, name.trim());
      navigate("/");
    } catch (error) {
      toast({ title: "Signup failed", description: error instanceof Error ? error.message : "Please try again.", variant: "destructive" });
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 gradient-surface">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-32 -left-32 w-[400px] h-[400px] rounded-full gradient-hero opacity-15 blur-3xl" />
        <div className="absolute -bottom-32 -right-32 w-[350px] h-[350px] rounded-full gradient-accent opacity-10 blur-3xl" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 40, scale: 0.92 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={spring}
        className="relative z-10 w-full max-w-md"
      >
        <div className="glass-card-elevated rounded-3xl p-8">
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...spring, delay: 0.1 }}
            className="text-center mb-8"
          >
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring" as const, stiffness: 400, damping: 15, delay: 0.2 }}
              className="w-14 h-14 rounded-2xl gradient-hero flex items-center justify-center mx-auto mb-4"
            >
              <Leaf className="w-7 h-7 text-primary-foreground" />
            </motion.div>
            <h1 className="text-2xl font-display font-bold">Create Account</h1>
            <p className="text-sm text-muted-foreground mt-1">Join AgroSense AI today</p>
          </motion.div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <motion.div
              initial={{ opacity: 0, x: -30 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ ...spring, delay: 0.12 }}
            >
              <Label htmlFor="name" className="text-sm font-medium mb-1.5 block">Full Name</Label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="name"
                  placeholder="John Doe"
                  value={name}
                  onChange={(e) => { setName(e.target.value); setErrors((current) => ({ ...current, name: undefined })); }}
                  className="pl-10 rounded-xl h-11"
                  aria-invalid={Boolean(errors.name)}
                  aria-describedby={errors.name ? "name-error" : undefined}
                  required
                />
              </div>
              {errors.name && <p id="name-error" className="mt-1.5 text-sm text-destructive">{errors.name}</p>}
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: -30 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ ...spring, delay: 0.17 }}
            >
              <Label htmlFor="email" className="text-sm font-medium mb-1.5 block">Email</Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => { setEmail(e.target.value); setErrors((current) => ({ ...current, email: undefined })); }}
                  className="pl-10 rounded-xl h-11"
                  aria-invalid={Boolean(errors.email)}
                  aria-describedby={errors.email ? "email-error" : undefined}
                  required
                />
              </div>
              {errors.email && <p id="email-error" className="mt-1.5 text-sm text-destructive">{errors.email}</p>}
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: -30 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ ...spring, delay: 0.22 }}
            >
              <Label htmlFor="password" className="text-sm font-medium mb-1.5 block">Password</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); setErrors((current) => ({ ...current, password: undefined })); }}
                  className="pl-10 rounded-xl h-11"
                  minLength={8}
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={errors.password ? "password-error" : undefined}
                  required
                />
              </div>
              {errors.password && <p id="password-error" className="mt-1.5 text-sm text-destructive">{errors.password}</p>}
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ ...spring, delay: 0.27 }}
            >
              <Button
                type="submit"
                size="lg"
                disabled={isLoading}
                className="w-full gradient-hero text-primary-foreground font-semibold rounded-xl h-12"
              >
                {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "Create Account"}
              </Button>
            </motion.div>
          </form>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.35 }}
            className="text-center text-sm text-muted-foreground mt-6"
          >
            Already have an account?{" "}
            <Link to="/login" className="text-primary font-semibold hover:underline">
              Sign In
            </Link>
          </motion.p>
        </div>
      </motion.div>
    </div>
  );
}
