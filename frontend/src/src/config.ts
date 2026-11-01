const requiredEnv = (name: keyof ImportMetaEnv): string => {
  const value = import.meta.env[name];
  if (!value) {
    throw new Error(`Missing ${name}. Add it to .env.local.`);
  }
  return value;
};

export const appConfig = {
  backendUrl: requiredEnv("VITE_BACKEND_URL"),
  firestoreEnabled: import.meta.env.VITE_FIRESTORE_ENABLED === "true",
  firebase: {
    apiKey: requiredEnv("VITE_FIREBASE_API_KEY"),
    authDomain: requiredEnv("VITE_FIREBASE_AUTH_DOMAIN"),
    projectId: requiredEnv("VITE_FIREBASE_PROJECT_ID"),
    storageBucket: requiredEnv("VITE_FIREBASE_STORAGE_BUCKET"),
    messagingSenderId: requiredEnv("VITE_FIREBASE_MESSAGING_SENDER_ID"),
    appId: requiredEnv("VITE_FIREBASE_APP_ID"),
    measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID,
  },
  map: {
    satelliteTiles: requiredEnv("VITE_SATELLITE_TILES_URL"),
    streetTiles: requiredEnv("VITE_STREET_TILES_URL"),
  },
} as const;
