#!/usr/bin/env python3

import asyncio
import argparse
import logging
import random
import urllib.parse
import time
import json # Benötigt für den POST-Body
from typing import List, Dict, Optional, Tuple, Any
import httpx

# --- Optionales Rich-Import ---
try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None
    Table = None
    Live = None

# Konfiguration
DEBUG: bool = False
SSL_VERIFY: bool = True
BANNER = 'Alpha 4.3 - Layer 7'

# Konstanten (Kontrollierte Werte für legale Tests)
METHOD_GET = 'get'
METHOD_POST = 'post'
METHOD_RAND = 'random'

# Kontrollierte Standardwerte
DEFAULT_WORKERS = 50    
DEFAULT_SOCKETS = 350
DEFAULT_RATE_LIMIT = 10000 # Sehr hoch, simuliert maximale Geschwindigkeit PRO WORKER

# User-Agents
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.10 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/134.0.6998.99 Mobile/15E148 Safari/604.1',
]

# Logging Setup
logging.basicConfig(level=logging.INFO if not DEBUG else logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
console = Console() if RICH_AVAILABLE else None


class Alpha:
    """Hauptklasse für Alpha 4.3"""

    def __init__(self, url: str, workers: int = DEFAULT_WORKERS, sockets: int = DEFAULT_SOCKETS,
                 method: str = METHOD_POST, # <--- HIER AUF POST GEÄNDERT
                 rate_limit: int = DEFAULT_RATE_LIMIT,
                 duration: Optional[int] = None, dry_run: bool = False):
        self.url = url
        self.workers = workers
        self.sockets = sockets
        self.method = method
        self.rate_limit = max(1, rate_limit)
        self.dry_run = dry_run
        self.duration = duration
        self.user_agents = USER_AGENTS
        
        self.counter: List[int] = [0, 0] # [Erfolge, Fehler]
        self.latencies: List[float] = [] # Latenz-Tracking
        self.start_time: float = 0.0
        self.running: bool = True
        
        self.parsed_url = urllib.parse.urlparse(url)
        self.base_url = f"{self.parsed_url.scheme}://{self.parsed_url.netloc}"
        self.path = self.parsed_url.path or '/'
        self.session: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self.start_time = time.time()
        if not self.dry_run:
            self.session = httpx.AsyncClient(
                base_url=self.base_url,
                verify=SSL_VERIFY,
                timeout=httpx.Timeout(15.0),
                limits=httpx.Limits(
                    max_keepalive_connections=self.sockets * 2,  
                    max_connections=self.workers * self.sockets * 2 
                ),
                http2=True 
            )
            logger.info(f"Session initialisiert für {self.base_url}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.running = False
        if self.session:
            await self.session.aclose()
        self.print_stats()

    def get_stats_table(self) -> Table:
        """Erweiterte Stats mit Latenz-Metriken."""
        success, failed = self.counter
        elapsed = time.time() - self.start_time
        total_requests = success + failed
        rate = total_requests / elapsed if elapsed > 0 else 0
        
        if self.latencies:
            avg_latency = sum(self.latencies) / len(self.latencies)
            max_latency = max(self.latencies)
        else:
            avg_latency = max_latency = 0

        table = Table(title=f"{self.url}", title_style="bold green")
        table.add_column("Metrik", style="cyan")
        table.add_column("Wert", style="magenta")

        table.add_row("Standard Methode", self.method.upper())
        table.add_row("RPS (Gesamt)", f"{rate:.2f}/s")
        table.add_row("Max. RPS (Pro Worker)", f"{self.rate_limit} RPS")
        table.add_row("Total Requests", str(total_requests))
        table.add_row("Erfolgreich (2xx/3xx)", str(success), style="green")
        table.add_row("Fehler (4xx/5xx/Timeout)", str(failed), style="red")
        table.add_row("Durchschn. Latenz", f"{avg_latency:.2f} ms", style="yellow")
        table.add_row("Max. Latenz", f"{max_latency:.2f} ms", style="yellow")
        table.add_row("Laufzeit", f"{elapsed:.2f} Sekunden")
        return table

    def print_header(self) -> None:
        if RICH_AVAILABLE and console:
            console.print(BANNER, style="bold green")
            console.print(f"Ziel: [cyan]{self.url}[/cyan] | Workers: [magenta]{self.workers}[/magenta] | Sockets/Cycle: [magenta]{self.sockets}[/magenta]", style="bold yellow")
            console.print(f"STANDARD METHODE: [bold red]{self.method.upper()}[/bold red]")
            console.print("HINWEIS: Alpha Version \n", style="bold red")
        else:
             print(f"{BANNER}\nZiel: {self.url} | Workers: {self.workers} | Standard Methode: {self.method.upper()}")

    def print_stats(self) -> None:
        if RICH_AVAILABLE and console:
            console.print(self.get_stats_table())
        else:
            # Fallback-Ausgabe (Logik wie in get_stats_table)
            success, failed = self.counter
            total_requests = success + failed
            elapsed_time = time.time() - self.start_time
            rps = total_requests / elapsed_time if elapsed_time > 0 else 0
            avg_lat = sum(self.latencies) / len(self.latencies) if self.latencies else 0
            
            print(f"\n--- Load-Test Stats ---")
            print(f"Methode: {self.method.upper()} | Total Requests: {total_requests}, RPS (Gesamt): {rps:.2f}")
            print(f"Erfolgreich: {success}, Fehler: {failed} | Avg Lat: {avg_lat:.2f}ms")

    def generate_request(self) -> Tuple[str, Dict[str, str], Optional[Dict]]:
        """Generiert einen zufälligen Request-Pfad, Header und optionalen Body."""
        # Zufälliger Query-Parameter für Cache Busting (normales Encoding)
        cache_buster = f"?q={random.randint(100000, 999999)}"
        url_path = f"{self.path}{cache_buster}"
        
        headers = {
            'User-Agent': random.choice(self.user_agents),
            'Connection': 'keep-alive',
            'Referer': f"{self.base_url}/search?q={random.randint(1000, 9999)}",
            'Accept-Encoding': 'gzip, deflate, br'
        }
        
        body: Optional[Dict[str, Any]] = None
        
        method = random.choice([METHOD_GET, METHOD_POST]) if self.method == METHOD_RAND else self.method

        if method.upper() == 'POST':
            headers['Content-Type'] = 'application/json'
            # Generiert einen einfachen, variierenden JSON-Payload
            body = {"key": f"data_{random.randint(1, 1000)}", "timestamp": int(time.time()), "worker_id": random.randint(1, self.workers)}
        
        return url_path, headers, body

    async def strike(self, url_path: str, headers: Dict[str, str], body: Optional[Dict]) -> bool:
        """Führt eine einzelne HTTP-Anfrage aus."""
        if self.dry_run:
            self.counter[0] += 1
            return True
        
        method = random.choice([METHOD_GET, METHOD_POST]) if self.method == METHOD_RAND else self.method
        
        start_time = time.perf_counter()
        success = False
        
        try:
            if method.upper() == 'GET':
                resp = await self.session.get(url_path, headers=headers)
            elif method.upper() == 'POST':
                # Sende JSON-Body für POST
                resp = await self.session.post(url_path, headers=headers, json=body)
            else:
                self.counter[1] += 1
                return False
                
            latency = (time.perf_counter() - start_time) * 1000 # ms
            self.latencies.append(latency)
                
            if 200 <= resp.status_code < 400:
                self.counter[0] += 1
                success = True
            else:
                # 4xx oder 5xx
                self.counter[1] += 1
                
        except httpx.HTTPError as e:
            logger.debug(f"HTTPX-Fehler: {e}")
            self.counter[1] += 1
        except Exception as e:
            logger.debug(f"Allgemeiner Request-Fehler: {e}")
            self.counter[1] += 1
        
        return success

    async def worker(self) -> None:
        """Der Worker-Task mit implementiertem Layer 7 Rate Limiting."""
        
        # Zeit, die gewartet werden muss, um das Limit einzuhalten (Sekunden pro Request)
        delay_per_request = 1.0 / self.rate_limit
        
        while self.running:
            tasks = []
            
            for _ in range(self.sockets):
                url_path, headers, body = self.generate_request()
                tasks.append(self.strike(url_path, headers, body))
                
                # Wartezeit vor dem nächsten Request, um das Limit einzuhalten
                await asyncio.sleep(delay_per_request)
                
            # Führe den Batch von Tasks parallel aus
            await asyncio.gather(*tasks)


    async def run(self) -> None:
        self.print_header()
        
        if self.dry_run:
            logger.info("Dry-Run aktiviert. Keine echten Requests werden gesendet.")
            await asyncio.sleep(1) # Kurze Pause für die dry-run Ausgabe
            return # Beendet den Dry-Run

        worker_tasks = [self.worker() for _ in range(self.workers)]
        
        try:
            if self.duration:
                logger.info(f"Starte Lasttest für {self.duration} Sekunden...")
                # Startet alle Worker und wartet, bis das Timeout erreicht ist
                await asyncio.wait([asyncio.create_task(t) for t in worker_tasks], timeout=self.duration) 
            else:
                logger.info("Starte Lasttest (unbegrenzt). Drücke Strg+C zum Stoppen...")
                await asyncio.gather(*worker_tasks)

        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.info("Lasttest manuell gestoppt.")
        finally:
            self.running = False


# --- Kommandozeilen-Logik ---
async def run_wrapper():
    parser = argparse.ArgumentParser(description=BANNER)
    parser.add_argument('url', help='Ziel-URL (z.B. https://example.com/api/submit)')
    parser.add_argument('-w', '--workers', type=int, default=DEFAULT_WORKERS, help=f'Anzahl der Worker (parallele Prozesse). Standard: {DEFAULT_WORKERS}')
    parser.add_argument('-s', '--sockets', type=int, default=DEFAULT_SOCKETS, help=f'Requests pro Zyklus pro Worker. Standard: {DEFAULT_SOCKETS}')
    parser.add_argument('-m', '--method', choices=[METHOD_GET, METHOD_POST, METHOD_RAND], default=METHOD_POST, help='HTTP-Methode (get, post, random). STANDARD: post')
    parser.add_argument('-d', '--duration', type=int, default=None, help='Testdauer in Sekunden (optional, unbegrenzt wenn weggelassen)')
    parser.add_argument('-r', '--rate-limit', type=int, default=DEFAULT_RATE_LIMIT, help=f'Max. Requests pro Sekunde PRO WORKER (RPS). Standard: {DEFAULT_RATE_LIMIT} (sehr hoch, simuliert max. Speed)')
    parser.add_argument('--dry-run', action='store_true', help='Testet nur die Logik, sendet keine Requests.')
    
    args = parser.parse_args()
    
    target_url = args.url

    async with Alpha(
        url=target_url,
        workers=args.workers,
        sockets=args.sockets,
        method=args.method,
        rate_limit=args.rate_limit,
        duration=args.duration,
        dry_run=args.dry_run
    ) as engine:
        await engine.run()


if __name__ == '__main__':
    try:
        asyncio.run(run_wrapper())
    except SystemExit:
        pass 
    except Exception as e:
        logger.error(f"Ein Fehler ist aufgetreten: {e}")