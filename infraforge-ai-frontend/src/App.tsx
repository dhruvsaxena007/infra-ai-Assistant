import React, { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import AssistantPage from "./components/Assistant/AssistantPage";
import SplashScreen from "./components/SplashScreen";

/**
 * The app opens with a premium splash screen, then transitions to the
 * Infra AI-Assistant for Marketplace experience.
 */
export default function App() {
  const [ready, setReady] = useState(false);

  return (
    <>
      <AnimatePresence mode="wait">
        {!ready && (
          <SplashScreen key="splash" onComplete={() => setReady(true)} />
        )}
      </AnimatePresence>

      {ready && (
        <motion.div
          key="app"
          className="h-dvh max-h-dvh overflow-hidden"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        >
          <AssistantPage />
        </motion.div>
      )}
    </>
  );
}
