export type Severity = "Critical" | "High" | "Moderate";

export type FloodZone = {
  id: string;
  region: string;
  city: string;
  state: string;
  severity: Severity;
  area: number;
  population: number;
  depth: number;
  change: number;
  category: "River basin" | "Urban flooding" | "Coastal risk" | "Mountain runoff";
  updatedAt: string;
  rating: number;
  image: string;
};

export const FLOOD_ZONES: FloodZone[] = [
  { id: "ludhiana-sutlej", region: "Sutlej floodplain", city: "Ludhiana", state: "Punjab", severity: "Critical", area: 42.8, population: 18420, depth: 2.8, change: 18.4, category: "River basin", updatedAt: "2025-08-24", rating: 4.9, image: "https://images.unsplash.com/photo-1547683905-f686c993aae5?auto=format&fit=crop&w=800&q=80" },
  { id: "patiala-ghaggar", region: "Ghaggar basin", city: "Patiala", state: "Punjab", severity: "High", area: 28.4, population: 11760, depth: 1.9, change: 11.2, category: "River basin", updatedAt: "2025-08-24", rating: 4.7, image: "https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=800&q=80" },
  { id: "kapurthala-beas", region: "Beas river corridor", city: "Kapurthala", state: "Punjab", severity: "Moderate", area: 16.7, population: 6980, depth: 1.1, change: 6.8, category: "River basin", updatedAt: "2025-08-24", rating: 4.4, image: "https://images.unsplash.com/photo-1473445361085-b9a07f55608b?auto=format&fit=crop&w=800&q=80" },
  { id: "mumbai-mithi", region: "Mithi urban corridor", city: "Mumbai", state: "Maharashtra", severity: "High", area: 31.6, population: 26500, depth: 1.6, change: 14.8, category: "Urban flooding", updatedAt: "2025-08-23", rating: 4.8, image: "https://images.unsplash.com/photo-1595658658481-d53d3f999875?auto=format&fit=crop&w=800&q=80" },
  { id: "guwahati-brahmaputra", region: "Brahmaputra lowlands", city: "Guwahati", state: "Assam", severity: "Critical", area: 54.2, population: 32100, depth: 3.2, change: 22.1, category: "River basin", updatedAt: "2025-08-22", rating: 4.9, image: "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=800&q=80" },
  { id: "kochi-backwaters", region: "Kochi backwater belt", city: "Kochi", state: "Kerala", severity: "Moderate", area: 19.8, population: 9100, depth: 1.2, change: 8.6, category: "Coastal risk", updatedAt: "2025-08-21", rating: 4.5, image: "https://images.unsplash.com/photo-1602216056096-3b40cc0c9944?auto=format&fit=crop&w=800&q=80" },
  { id: "kolkata-delta", region: "Hooghly delta edge", city: "Kolkata", state: "West Bengal", severity: "High", area: 37.5, population: 20400, depth: 1.8, change: 15.6, category: "Coastal risk", updatedAt: "2025-08-20", rating: 4.6, image: "https://images.unsplash.com/photo-1558431382-27e303142255?auto=format&fit=crop&w=800&q=80" },
  { id: "chennai-adyar", region: "Adyar basin", city: "Chennai", state: "Tamil Nadu", severity: "High", area: 24.9, population: 15600, depth: 1.5, change: 12.4, category: "Urban flooding", updatedAt: "2025-08-19", rating: 4.7, image: "https://images.unsplash.com/photo-1582510003544-4d00b7f74220?auto=format&fit=crop&w=800&q=80" },
  { id: "hyderabad-musi", region: "Musi urban reach", city: "Hyderabad", state: "Telangana", severity: "Moderate", area: 13.4, population: 7300, depth: .9, change: 5.2, category: "Urban flooding", updatedAt: "2025-08-18", rating: 4.3, image: "https://images.unsplash.com/photo-1572445271230-a78b5944a659?auto=format&fit=crop&w=800&q=80" },
  { id: "dehradun-rispana", region: "Rispana foothills", city: "Dehradun", state: "Uttarakhand", severity: "High", area: 21.3, population: 8400, depth: 1.4, change: 10.1, category: "Mountain runoff", updatedAt: "2025-08-17", rating: 4.6, image: "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=800&q=80" },
];
