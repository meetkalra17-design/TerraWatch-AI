import { getAuth } from "firebase/auth";
import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
import { appConfig } from "./config";

const app = initializeApp(appConfig.firebase);

export const auth = getAuth(app);
export const getDb = () => getFirestore(app);
