import sys
import argparse
sys.stdout.reconfigure(encoding='utf-8')
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os

doc = Document()

# ── Page setup ──
for section in doc.sections:
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)

style = doc.styles['Normal']
style.font.name = 'Consolas'
style.font.size = Pt(9.5)
style.paragraph_format.space_after = Pt(1)
style.paragraph_format.space_before = Pt(1)

def add_heading_text(text, size=14, bold=True, color=RGBColor(0x1F, 0x38, 0x64), align=WD_ALIGN_PARAGRAPH.LEFT):
    p = doc.add_paragraph()
    p.alignment = align
    r = p.add_run(text)
    r.bold = bold
    r.font.size = Pt(size)
    r.font.color.rgb = color
    r.font.name = 'Arial'
    return p

def add_line(text, size=9.5, bold=False, color=RGBColor(0x1A, 0x1A, 0x1A), indent=0):
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.left_indent = Cm(indent)
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.bold = bold
    r.font.color.rgb = color
    r.font.name = 'Consolas'
    return p

def date_header(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(11)
    r.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
    r.font.name = 'Consolas'
    # Add yellow background
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'), 'FFF2CC')
    shd.set(qn('w:val'), 'clear')
    rpr = r._element.get_or_add_rPr()
    rpr.append(shd)
    return p

def section_tag(text, color='D9E1F2'):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(f'  [{text}]')
    r.bold = True
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(0x1F, 0x38, 0x64)
    r.font.name = 'Arial'
    return p

def bullet(text, indent=0.5):
    return add_line(f'  • {text}', indent=indent)

def practice(text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    r = p.add_run(f'  ▶ PRACTICE: {text}')
    r.bold = True
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(0x70, 0x30, 0xA0)
    r.font.name = 'Consolas'
    return p

def divider():
    p = doc.add_paragraph()
    r = p.add_run('─' * 80)
    r.font.size = Pt(6)
    r.font.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)

def phase_header(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor(0x1F, 0x38, 0x64)
    r.font.name = 'Arial'

# ══════════════════════════════════════════════════════════
# TITLE
# ══════════════════════════════════════════════════════════

add_heading_text('SDE PLACEMENT ROADMAP — REMAINING PLAN', size=16, align=WD_ALIGN_PARAGRAPH.CENTER)
add_line('May 24, 2026 → July 31, 2026  |  Freshers  |  Internship + On/Off-Campus SDE', size=9, color=RGBColor(0x59,0x59,0x59))
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run('PENDING ONLY — All completed items excluded')
r.font.size = Pt(9)
r.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
r.italic = True

# ── COMPLETED SUMMARY ──
add_heading_text('ALREADY COMPLETED — EXCLUDED', size=11)
for item in [
    'Main Project — built + deployed',
    'Deployment — live on VPS',
    'Portfolio — complete',
    '4 LiteLLM PRs — raised (pending merge)',
    'DSA: Arrays, Binary Search, Strings, Linked List, Stacks & Queues, Sliding Window'
]:
    add_line(f'  ✓ {item}', color=RGBColor(0x37, 0x56, 0x23), bold=True)

add_heading_text('DAILY SCHEDULE TEMPLATE (Mon-Sat)', size=11)
for slot in [
    '7:00-9:00 AM   → DSA Topic (new concept + 3-4 problems)',
    '9:00-10:00 AM  → Exercise + Breakfast',
    '10:00 AM-1:00 PM → DSA Deep Practice (8-10 problems on today\'s topic)',
    '1:00-2:00 PM   → Lunch + Rest',
    '2:00-4:00 PM   → Core Subject (OS/DBMS/CN/OOP — one per phase)',
    '4:00-5:00 PM   → Break',
    '5:00-7:00 PM   → DevOps / Project Polish / Open Source',
    '7:00-8:00 PM   → Dinner',
    '8:00-9:00 PM   → Resume / LinkedIn / GitHub',
    '9:00-10:00 PM  → Behavioral + HR Prep',
    '10:30 PM       → Sleep',
]:
    add_line(f'  {slot}', size=8.5)

add_line('  LC Milestones: ~150 (End Wk2) → ~300 (End Wk4) → ~500 (End Wk6) → 950+ (End July)', size=8.5, bold=True, color=RGBColor(0xC0,0x00,0x00))

# ══════════════════════════════════════════════════════════
# PHASE 1: DSA + CORE SUBJECTS (May 24 – June 28)
# ══════════════════════════════════════════════════════════

phase_header('═══  PHASE 1 — DSA COMPLETION + CORE SUBJECTS  (May 24 – June 28)  ═══')

# ── MAY 24 ──
date_header('MAY 24 (SAT)')
section_tag('DSA: Two Pointers + Hashing  [1 day]')
bullet('Two Pointers: fixed/variable window, 3-sum, container water, trapping rain water')
bullet('Hashing: HashMap/HashSet, frequency maps, two-sum family, anagram checks')
bullet('Longest substring without repeating chars, group anagrams, longest consecutive sequence')
practice('LeetCode — Two Pointers: #11, #15, #167, #283, #42  |  Hashing: #1, #49, #128, #560, #3')
section_tag('OS: Day 1 — Processes')
bullet('Process vs Program, PCB structure, process states (New/Ready/Running/Waiting/Terminated)')
bullet('State transitions, fork() + exec() semantics, zombie + orphan processes')
practice('GFG OS MCQs — Processes section (15 Qs)')
section_tag('Evening Tasks')
bullet('Resume: Add completed project with action verbs + metrics (response time, API calls, users)')
bullet('GitHub: Push final project code, update project README with architecture diagram')
divider()

# ── MAY 25 ──
date_header('MAY 25 (SUN)')
section_tag('DSA: Recursion  [1 day]')
bullet('Recursion tree visualization, subsets (power set), permutations, power(x,n)')
bullet('Memoization intro (top-down), recursion vs iteration tradeoff, call stack depth')
practice('LeetCode — #78 (Subsets), #46 (Permutations), #50 (Pow x,n), #394 (Decode String), #779')
section_tag('OS: Day 2 — Threads')
bullet('Threads vs Processes (shared memory, heap, file descriptors)')
bullet('User-level vs Kernel-level threads, M:1 / 1:1 / M:M threading models')
bullet('Context switch cost, thread creation overhead, advantages of multithreading')
practice('GFG OS MCQs — Threads section (10 Qs)')
section_tag('Evening — CONTEST')
bullet('LeetCode Weekly Contest (mandatory Sunday ritual — do not skip)')
bullet('Post-contest: review every unsolved problem, read editorial, recode from scratch')
divider()

# ── MAY 26 ──
date_header('MAY 26 (MON)')
section_tag('DSA: Backtracking  [1 day]')
bullet('Decision tree approach, pruning (prune when constraint violated, not after)')
bullet('N-Queens, Sudoku solver, Word search, Combination sum I/II, Letter combinations')
bullet('Palindrome partitioning, Rat in a maze, Permutations with duplicates')
practice('LeetCode — #51 (N-Queens), #37 (Sudoku Solver), #79 (Word Search), #39 (Combo Sum), #131')
section_tag('OS: Day 3 — CPU Scheduling')
bullet('FCFS (convoy effect), SJF (preemptive=SRTF, non-preemptive, starvation)')
bullet('Round Robin (quantum size effect), Priority Scheduling + aging, MLFQ')
practice('GFG — Solve 3 Gantt chart problems by hand (FCFS, SJF, RR). 10 OS MCQs.')
section_tag('Evening Tasks')
bullet('DevOps: GitHub Actions CI pipeline setup for project (lint + test on push)')
bullet('LinkedIn: Draft project post (architecture + tech stack)')
divider()

# ── MAY 27 ──
date_header('MAY 27 (TUE)')
section_tag('DSA: Binary Trees Part 1  [2 days — Day 1]')
bullet('Inorder/Preorder/Postorder: recursive + iterative (stack-based)')
bullet('Level-order BFS (queue), Height, Diameter, Symmetric, Balanced check')
bullet('Count nodes, Same tree, Path sum I/II, Invert binary tree')
practice('LeetCode — #94, #144, #145, #102 (Level Order), #104, #543, #226, #110, #101, #112')
section_tag('OS: Day 4 — Synchronization')
bullet('Race conditions, Critical section (mutual exclusion + progress + bounded wait)')
bullet('Mutex, Semaphores (binary vs counting), Monitors, wait()/signal()')
bullet('Producer-Consumer, Dining Philosophers, Readers-Writers')
practice('GFG OS MCQs — Synchronization (15 Qs). Solve Producer-Consumer by hand.')
section_tag('Evening Tasks')
bullet('DevOps: Docker networking review, Docker Compose verify on project')
bullet('Open Source: Comment on all 4 LiteLLM PRs — ask for review, update if needed')
divider()

# ── MAY 28 ──
date_header('MAY 28 (WED)')
section_tag('DSA: Binary Trees Part 2  [2 days — Day 2]')
bullet('LCA (recursive + iterative), Max path sum (any-to-any)')
bullet('Serialize/Deserialize, Left/Right/Top/Bottom view, ZigZag level-order')
bullet('Count nodes in complete tree O(log²n), Flatten tree to linked list')
practice('LeetCode — #236 (LCA), #124 (Max Path Sum), #297 (Serialize), #199, #103 (ZigZag), #114')
section_tag('OS: Day 5 — Deadlocks')
bullet('4 conditions: Mutual Exclusion, Hold & Wait, No Preemption, Circular Wait')
bullet('Prevention (negate one), Avoidance: Banker\'s Algorithm (safe state)')
bullet('Detection (resource allocation graph, wait-for graph), Recovery')
practice('GFG — Solve 2 Banker\'s Algorithm problems by hand. 10 OS MCQs on deadlocks.')
section_tag('Evening Tasks')
bullet('DevOps: Nginx setup basics + reverse proxy config for project')
bullet('Resume: Add DevOps skills section with Docker, GitHub Actions, Nginx')
divider()

# ── MAY 29 ──
date_header('MAY 29 (THU)')
section_tag('DSA: BST — Binary Search Tree  [1 day]')
bullet('BST property, Search/Insert/Delete (all 3 delete cases), Time complexity')
bullet('Kth smallest/largest (inorder), Validate BST (range-based)')
bullet('BST to sorted doubly LL, Sorted array to balanced BST, Recover BST, Floor/Ceil')
practice('LeetCode — #700, #701, #450, #230 (Kth Smallest), #98 (Validate), #108, #653, #285')
section_tag('OS: Day 6 — Memory Management')
bullet('Contiguous alloc, Fixed/variable partitioning, Internal vs external fragmentation')
bullet('Paging: page table, logical→physical translation, page size effect')
bullet('Segmentation, TLB: hit ratio + effective access time, Multi-level page tables')
practice('GFG OS MCQs — Memory (15 Qs). Solve 2 address translation problems (pages + TLB).')
section_tag('Evening Tasks')
bullet('DevOps: SSL/TLS setup for deployed project (Let\'s Encrypt / Certbot)')
bullet('GitHub: Update project README with architecture diagram')
divider()

# ── MAY 30 ──
date_header('MAY 30 (FRI)')
section_tag('DSA: Heap / Priority Queue  [1 day]')
bullet('Max-heap vs Min-heap (heapify up/down), Heap sort')
bullet('Top-K elements (kth largest, kth most frequent), Merge K sorted lists')
bullet('Median from data stream (two heaps), Task scheduler, K closest points, Sliding window max')
practice('LeetCode — #215, #347, #23 (Merge K Lists), #295 (Median), #621 (Task Scheduler), #973, #239')
section_tag('OS: Day 7 — Virtual Memory')
bullet('Demand paging, Page fault handling (6 steps: trap→frame→load→update→restart)')
bullet('Page replacement: FIFO, LRU (stack/clock), Optimal (Belady)')
bullet('Belady\'s anomaly (FIFO only), Thrashing, Working set model')
practice('GFG — Solve 3 page replacement problems by hand (FIFO, LRU, Optimal). 10 MCQs.')
section_tag('Evening Tasks')
bullet('Pytest: Write integration tests for project API (3-5 test cases)')
bullet('Open Source: Identify next LiteLLM issue to raise PR for (browse open issues)')
divider()

# ── MAY 31 ──
date_header('MAY 31 (SAT)')
section_tag('DSA: Practice Day  [Week review]')
bullet('8-10 LC mediums: mix of Recursion, Backtracking, Trees, BST, Heap')
bullet('1 timed 45-min OA simulation: pick past LeetCode weekly contest (virtual mode)')
bullet('Record all patterns where you needed hints — revisit after contest')
practice('LeetCode Virtual Contest OR Codeforces Div 2 (virtual). Track weak patterns.')
section_tag('OS: Day 8 — File Systems + IPC  →  OS COMPLETE')
bullet('File system structure, Inodes, Directory structure, File allocation methods')
bullet('Disk scheduling: FCFS, SSTF, SCAN (elevator), C-SCAN, LOOK')
bullet('IPC: Pipes (anonymous, named/FIFO), Shared Memory, Message Queues, Signals')
practice('15 rapid-fire OS Q&A spoken aloud (all 8 days). GFG OS Practice Set — 20 mixed MCQs.')
section_tag('Evening — OS COMPLETE')
bullet('Write 1-page OS cheat sheet: scheduling formulas, Banker\'s steps, page replacement comparison')
divider()

# ── JUN 1 ──
date_header('JUNE 1 (SUN)')
section_tag('DSA: Greedy  [1 day]')
bullet('Activity selection (sort by finish time), Fractional knapsack')
bullet('Jump Game I (can reach end?), Jump Game II (min jumps — greedy)')
bullet('Meeting Rooms I/II, Gas station (circular tour), Candy, Assign cookies, Min platforms')
practice('LeetCode — #55, #45, #435, #134 (Gas Station), #135 (Candy), #452 (Balloons), #605')
section_tag('DBMS: Day 1 — ER Model + Relational Model')
bullet('Entity types (strong/weak), Attributes (simple/composite/multivalued/derived)')
bullet('Relationships, Cardinality (1:1, 1:N, M:N), Total vs partial participation')
bullet('Keys: Primary, Foreign, Candidate, Super, Alternate, Composite')
bullet('Integrity constraints: entity integrity, referential integrity')
practice('GFG DBMS MCQs — ER Model (10 Qs). Draw ER diagram for mini college DB from scratch.')
section_tag('Evening — CONTEST')
bullet('LeetCode Weekly Contest (Sunday mandatory)')
bullet('Post-contest review: recode unsolved from scratch')
divider()

# ── JUN 2 ──
date_header('JUNE 2 (MON)')
section_tag('DSA: Trie  [1 day]')
bullet('Trie node structure (children array/hashmap, isEnd flag), Insert/Search/Delete O(L)')
bullet('Word search II (Trie+backtracking), Prefix matching, Longest common prefix')
bullet('Auto-complete pattern, Count words with prefix, Replace words')
practice('LeetCode — #208 (Implement Trie), #212 (Word Search II), #211, #720, #677, #648')
section_tag('DBMS: Day 2 — Normalization')
bullet('Functional dependencies (FD), Attribute closure, Canonical cover')
bullet('1NF (atomic), 2NF (no partial dep on composite PK), 3NF (no transitive dep)')
bullet('BCNF (every determinant is candidate key), Decomposition: lossless join + dep preservation')
practice('GFG — Solve 3 normalization problems (schema→FDs→normalize to BCNF). 10 MCQs.')
section_tag('Evening Tasks')
bullet('DevOps: API testing (Postman collection for all project endpoints)')
bullet('Open Source: Find 1 new LiteLLM issue to work on')
divider()

# ── JUN 3 ──
date_header('JUNE 3 (TUE)')
section_tag('DSA: Bit Manipulation + OA Math  [1 day]')
bullet('XOR tricks: missing number, single number, two non-repeating numbers')
bullet('Count set bits: Brian Kernighan (n & n-1), Power of 2 check, bit masking')
bullet('GCD/LCM (Euclidean), Sieve of Eratosthenes, Modular arithmetic, Fast exponentiation')
practice('LeetCode — #136, #191, #231, #268, #201, #50 (Pow x,n), #204 (Count Primes), #29')
section_tag('DBMS: Day 3 — SQL Deep Dive')
bullet('Joins: INNER, LEFT/RIGHT/FULL OUTER, CROSS, SELF — with use cases')
bullet('Subqueries: correlated vs non-correlated, CTEs (WITH clause), Recursive CTEs')
bullet('Window functions: ROW_NUMBER, RANK, DENSE_RANK, LEAD, LAG, FIRST_VALUE')
bullet('SUM/AVG OVER (PARTITION BY), HAVING vs WHERE, UNION vs UNION ALL, EXISTS vs IN')
practice('LeetCode SQL — #175, #176, #177, #178, #180, #181, #184, #185. All mediums/hards.')
section_tag('Evening Tasks')
bullet('DevOps: Integration tests (pytest — auth, API responses, error handling)')
bullet('LinkedIn: Post 1 — Project architecture post (diagram + tech choices + lessons)')
divider()

# ── JUN 4 ──
date_header('JUNE 4 (WED)')
section_tag('DSA: Graphs Part 1 — BFS + DFS  [4 days — Day 1]')
bullet('Adjacency list vs matrix (space/time tradeoffs), Weighted vs unweighted')
bullet('BFS: queue-based, level-order, 0-1 BFS (deque), shortest path unweighted')
bullet('DFS: recursive + iterative (stack), pre/post order, back edges')
bullet('Connected components, Bipartite check (2-color), Flood fill')
practice('LeetCode — #200 (Islands), #994 (Rotten Oranges), #733, #785 (Bipartite), #1091, #417')
section_tag('DBMS: Day 4 — Indexing')
bullet('B-Tree: balanced, sorted, O(log n) — default in Postgres/MySQL')
bullet('Hash index: O(1) equality only, Clustered vs Non-clustered, Covering index')
bullet('Composite index prefix rule (a,b,c → works for a, a+b, a+b+c only)')
bullet('When NOT to index: low-cardinality, small tables, write-heavy cols')
practice('GFG DBMS MCQs — Indexing (10 Qs). Write 3 CREATE INDEX + run EXPLAIN on each.')
section_tag('Evening Tasks')
bullet('GitHub: Clean up all repos — descriptions, topics, proper READMEs')
bullet('Resume: Add database + indexing skills with project context')
divider()

# ── JUN 5 ──
date_header('JUNE 5 (THU)')
section_tag('DSA: Graphs Part 2 — Cycle Detection + Topological Sort  [Day 2]')
bullet('Cycle in undirected: DFS (back edge) + DSU (same component → cycle)')
bullet('Cycle in directed: DFS with 3-color (white/gray/black) or visited+recStack')
bullet('Topo sort DFS: push to stack at post-order, reverse')
bullet('Kahn\'s BFS topo: in-degree array, enqueue 0-in-degree, reduce neighbors')
bullet('Course schedule (detect cycle = impossible), All ancestors in DAG')
practice('LeetCode — #207 (Course Schedule), #210 (CS II), #684, #802 (Safe Nodes), #1203')
section_tag('DBMS: Day 5 — Transactions + ACID')
bullet('Atomicity (commit/rollback), Consistency, Isolation, Durability (WAL)')
bullet('Isolation levels: Read Uncommitted → Read Committed → Repeatable Read → Serializable')
bullet('Problems by level: Dirty read (RU), Non-repeatable read (RC), Phantom read (RR)')
bullet('BEGIN/COMMIT/ROLLBACK, SAVEPOINT, implicit vs explicit transactions')
practice('GFG DBMS MCQs — Transactions (10 Qs). 5 scenario Q&A spoken aloud.')
section_tag('Evening Tasks')
bullet('DevOps: GitHub Actions CI/CD polish (add test stage, deploy on main branch)')
bullet('Open Source: Work on LiteLLM issue — push code for new/existing PR')
divider()

# ── JUN 6 ──
date_header('JUNE 6 (FRI)')
section_tag('DSA: Graphs Part 3 — Shortest Path  [Day 3]')
bullet('Dijkstra\'s: min-heap, greedy relaxation, O((V+E)logV), no negative weights')
bullet('Bellman-Ford: relax all edges V-1 times, O(VE), handles negative weights')
bullet('Negative cycle detection (if relaxation possible at step V → cycle)')
bullet('Why Dijkstra fails with negative weights, Shortest path in DAG')
practice('LeetCode — #743 (Network Delay), #787 (Cheapest K Stops), #1631, #1514, #505')
section_tag('DBMS: Day 6 — SQL Practice')
bullet('Write 10 SQL queries from scratch WITHOUT notes: joins, subqueries, window functions')
bullet('20 DBMS theory Q&A spoken aloud (5 per area: ER, Normalization, SQL, Transactions)')
practice('LeetCode SQL Hard — #185, #262, #569, #571')
section_tag('Evening Tasks')
bullet('Behavioral: Write STAR story #1 — biggest challenge overcome during the project')
bullet('LC Weekly Contest prep (review past contest patterns)')
divider()

# ── JUN 7 ──
date_header('JUNE 7 (SAT)')
section_tag('DSA: Graphs Part 4 + DSU  [Day 4]')
bullet('Kruskal MST: sort edges, pick min if no cycle (DSU) — O(E log E)')
bullet('Prim MST: start from any vertex, greedy min edge — O(E log V)')
bullet('Floyd-Warshall: all-pairs shortest path O(V³), dp[i][j] via intermediate k')
bullet('DSU: Union by rank (attach smaller tree), Path compression (point to root)')
bullet('Amortized O(1) per operation (inverse Ackermann)')
practice('LeetCode — #1584, #1135, #684, #685, #547 (Provinces), #399 (Evaluate Division)')
section_tag('DBMS: Day 7 — Concurrency Control')
bullet('2-Phase Locking: growing phase (acquire), shrinking phase (release)')
bullet('Strict 2PL (hold exclusive locks until commit), Conservative 2PL')
bullet('MVCC: readers don\'t block writers (Postgres default)')
bullet('Deadlocks in DBMS: wait-for graph cycle detection, timeout-based')
practice('GFG — 10 MCQs concurrency control. 5 scenario Q&A spoken aloud.')
section_tag('Evening — PRACTICE')
bullet('8-10 LC mediums: Graphs mix (BFS/DFS/Topo/Dijkstra/DSU)')
divider()

# ── JUN 8 ──
date_header('JUNE 8 (SUN)')
section_tag('DSA: Sorting Algorithms  [1 day]')
bullet('Merge Sort: divide+conquer, O(n log n) stable, O(n) space — implement from scratch')
bullet('Quick Sort: partition (Lomuto/Hoare), O(n log n) avg / O(n²) worst — implement')
bullet('Counting Sort: O(n+k), non-comparative, stable — implement')
bullet('Radix Sort: digit-by-digit (LSD), O(d(n+b)), stable — implement')
practice('LeetCode — #912 (Sort Array), #315 (Count Smaller), #493 (Reverse Pairs). Implement all 4 from scratch.')
section_tag('DBMS: Day 8 — Query Optimization')
bullet('EXPLAIN + EXPLAIN ANALYZE: Seq Scan vs Index Scan vs Bitmap Scan')
bullet('Cost-based optimizer: row estimates, join order selection')
bullet('N+1 query problem (ORM) — detect and fix with eager loading/JOINs')
bullet('Query rewriting: push predicates early, avoid SELECT *, covering indexes')
practice('Run EXPLAIN ANALYZE on 3 project queries. Fix slowest with an index.')
section_tag('Evening — CONTEST')
bullet('LeetCode Weekly Contest (Sunday mandatory)')
bullet('Post-contest review: recode every unsolved problem')
divider()

# ── JUN 9 ──
date_header('JUNE 9 (MON)')
section_tag('DSA: DP Part 1 — 1D Patterns  [5 days — Day 1]')
bullet('Top-down (memoization) vs Bottom-up (tabulation): state + recurrence + base case')
bullet('Fibonacci, Climbing Stairs (=Fibonacci), House Robber I (max non-adjacent)')
bullet('House Robber II (circular — two passes), Coin Change I (min coins), Coin Change II (ways)')
bullet('Decode Ways, Jump Game DP vs Greedy comparison')
practice('LeetCode — #70, #198, #213, #322 (Coin Change), #518 (CC II), #91, #509, #740')
section_tag('DBMS: Day 9 — Stored Procedures, Triggers, Views')
bullet('Stored procedures: parameterized, IN/OUT, CALL syntax')
bullet('Triggers: BEFORE/AFTER INSERT/UPDATE/DELETE, FOR EACH ROW/STATEMENT')
bullet('Views: virtual table, CREATE VIEW, updatable vs non-updatable')
bullet('Materialized Views: stored result, REFRESH MATERIALIZED VIEW')
practice('Write 1 stored procedure, 1 trigger (audit log), 1 materialized view for project DB.')
section_tag('Evening Tasks')
bullet('DevOps: Health check endpoint + structured JSON logging')
bullet('Resume: Quantify all project metrics (P95 latency, RPS, data volume)')
divider()

# ── JUN 10 ──
date_header('JUNE 10 (TUE)')
section_tag('DSA: DP Part 2 — 2D / Grid DP  [Day 2]')
bullet('Unique Paths: dp[i][j] = dp[i-1][j] + dp[i][j-1], space-optimize to O(n)')
bullet('Min Path Sum, Maximal Square: dp[i][j] = min(left,top,diag)+1')
bullet('Triangle (bottom-up from last row), Min Falling Path Sum')
bullet('Cherry Pickup (3D DP: two pointers simultaneously)')
practice('LeetCode — #62, #63 (Obstacles), #64, #221 (Maximal Square), #741, #120, #931')
section_tag('DBMS: Day 10 — PostgreSQL Internals')
bullet('VACUUM: removes dead tuples, reclaims space, updates visibility map')
bullet('AUTOVACUUM: tune via autovacuum_vacuum_scale_factor')
bullet('TOAST: columns >~2KB stored separately, Connection pooling: PgBouncer')
bullet('pg_stat_statements: tracks slow queries, WAL: crash recovery')
practice('Run pg_stat_statements on project DB. Identify top 3 slowest queries. Add indexes.')
section_tag('Evening Tasks')
bullet('Open Source: Push updates to pending LiteLLM PRs (address review comments)')
bullet('GitHub: Pin top 3 repositories (project, algo practice, open source)')
divider()

# ── JUN 11 ──
date_header('JUNE 11 (WED)')
section_tag('DSA: DP Part 3 — Knapsack Patterns  [Day 3]')
bullet('0/1 Knapsack: dp[i][w] = max(exclude, include), optimize to 1D (reverse)')
bullet('Unbounded Knapsack: item reuse, 1D dp forward iteration')
bullet('Subset Sum (boolean DP), Count subsets with sum, Partition Equal Subset Sum')
bullet('Target Sum (+/-), Last Stone Weight II, Ones and Zeroes (2D knapsack)')
practice('LeetCode — #416 (Partition Equal), #494 (Target Sum), #474, #1049, #879')
section_tag('DBMS: Day 11 — Complete Revision')
bullet('40 theory + SQL Q&A spoken aloud — 10 per area: ER, Normalization, SQL, Transactions')
bullet('Write 5 complex SQL cold: rank within group, running total, 2nd highest salary, gaps')
practice('GFG DBMS Practice Set. InterviewBit DBMS section.')
section_tag('Evening Tasks')
bullet('Behavioral: Write STAR story #2 — conflict resolution during development')
bullet('HR: Record 2-min \'Tell me about yourself\' — listen back, time it')
divider()

# ── JUN 12 ──
date_header('JUNE 12 (THU)')
section_tag('DSA: DP Part 4 — String DP  [Day 4]')
bullet('LCS: dp[i][j] based on char match/mismatch, O(mn)')
bullet('Edit Distance: insert/delete/replace — dp[i][j] = 1+min(left,top,diag)')
bullet('Longest Palindromic Subsequence (reverse+LCS), Longest Palindromic Substring')
bullet('Interleaving Strings, Distinct Subsequences, Shortest Common Supersequence')
practice('LeetCode — #1143 (LCS), #72 (Edit Distance), #516, #5, #97, #115, #1092')
section_tag('DBMS: Day 12 — DBMS Mock  →  DBMS COMPLETE')
bullet('20-question timed interview sim (30 min) — no notes')
bullet('Write 5 complex SQL cold: running avg, nth salary, dept comparison')
bullet('Compile DBMS cheat sheet (1 page: all key formulas + concepts)')
practice('InterviewBit DBMS mock. LeetCode SQL contest problems (hard).')
section_tag('Evening — DBMS COMPLETE')
bullet('DevOps: Full pipeline review (GitHub Actions → Docker → Nginx → VPS)')
bullet('LinkedIn: Post 2 — Database design decisions (indexes, transactions, pooling)')
divider()

# ── JUN 13 ──
date_header('JUNE 13 (FRI)')
section_tag('DSA: DP Part 5 — Advanced DP  [Day 5]')
bullet('LIS: O(n²) DP + O(n log n) patience sorting (bisect)')
bullet('Russian Dolls (2D LIS), Matrix Chain Multiplication (interval DP)')
bullet('DP on Trees: House Robber III (include/exclude root, postorder DFS)')
bullet('Bitmask DP intro: TSP-lite dp[mask][node] = min cost')
practice('LeetCode — #300 (LIS), #354 (Russian Dolls), #1000, #337 (House Robber III), #1416')
section_tag('CN: Day 1 — OSI Model + TCP/IP')
bullet('OSI 7 layers + function: Physical, Data Link, Network, Transport, Session, Presentation, App')
bullet('TCP/IP 4-layer model mapping, Protocol stack, PDU names per layer')
bullet('Encapsulation/Decapsulation, Protocol examples per layer')
practice('GFG CN MCQs — OSI/TCP-IP (15 Qs). Draw OSI from memory + match protocols to layers.')
section_tag('Evening Tasks')
bullet('3 LC mediums on all DP patterns (timed, no hints)')
bullet('Open Source: Raise 1 new PR on LiteLLM or another open source Python project')
divider()

# ── JUN 14 ──
date_header('JUNE 14 (SAT)')
section_tag('DSA: Practice Day — Full DP Revision + MOCK OA #1')
bullet('8-10 LC mediums/hards across all 5 DP patterns')
bullet('MOCK OA #1: Full 2.5-hr timed OA (LeetCode virtual / Codeforces Div 2)')
bullet('Post-OA review: recode every unsolved from scratch, read editorial')
bullet('Note: which DP types you can\'t solve without hints')
practice('LeetCode Virtual Contest (past biweekly). Codeforces Virtual Div 2.')
section_tag('CN: Day 2 — TCP vs UDP')
bullet('TCP: connection-oriented, reliable, ordered, flow/congestion control')
bullet('UDP: connectionless, unreliable, fast — DNS, video, gaming')
bullet('3-way handshake: SYN → SYN-ACK → ACK')
bullet('4-way termination: FIN → ACK → FIN → ACK (half-close)')
bullet('Sliding window, AIMD congestion control (slow start → CA → SS)')
practice('GFG CN MCQs — TCP/UDP (10 Qs). Explain 3-way handshake aloud step-by-step.')
divider()

# ── JUN 15 ──
date_header('JUNE 15 (SUN)')
section_tag('DSA: Advanced Graphs  [1 day]')
bullet('Bridges: edge removal disconnects, Tarjan\'s — discovery time + low value')
bullet('Articulation Points: vertex removal increases components')
bullet('SCC: Kosaraju\'s — DFS original (finish stack) + DFS transposed (stack order)')
bullet('Euler Path (every edge once) vs Euler Circuit (start=end), Hierholzer\'s')
practice('LeetCode — #1192 (Critical Connections=Bridges), #1568. Codeforces bridge/AP problems.')
section_tag('CN: Day 3 — HTTP + REST + WebSockets')
bullet('HTTP/1.1: persistent connections, pipelining (HOL blocking)')
bullet('HTTP/2: multiplexing, HPACK compression, server push')
bullet('HTTP/3: QUIC (UDP), 0-RTT, no HOL at transport')
bullet('HTTPS=HTTP+TLS, Methods: GET/POST/PUT/PATCH/DELETE/OPTIONS/HEAD')
bullet('Status codes: 1xx/2xx/3xx/4xx/5xx, REST: stateless, resource-based URLs')
bullet('WebSocket: persistent bidirectional, HTTP Upgrade, chat/real-time use cases')
practice('GFG CN MCQs — HTTP (10 Qs). Explain REST vs WebSocket tradeoff aloud 2 min.')
section_tag('Evening — CONTEST')
bullet('LeetCode Weekly Contest (Sunday mandatory)')
divider()

# ── JUN 16 ──
date_header('JUNE 16 (MON)')
section_tag('DSA: Segment Tree  [1 day]')
bullet('Build O(n), array-based (1-indexed, node i → 2i, 2i+1)')
bullet('Range sum/min/max query O(log n), Point update O(log n)')
bullet('Lazy propagation: pending updates, push down before recurse — range update O(log n)')
practice('CSES — Range Sum Queries I+II, Range Min. LeetCode #307 (Range Sum Mutable), #315')
section_tag('CN: Day 4 — DNS + TLS + Subnetting')
bullet('DNS: browser cache → OS cache → recursive resolver → root NS → TLD NS → auth NS')
bullet('Records: A, AAAA, CNAME, MX, NS, TXT')
bullet('TLS handshake: ClientHello → ServerHello → Certificate → Key Exchange → Finished')
bullet('Certificate chain, CA hierarchy, HSTS, OCSP stapling')
bullet('CIDR (/24=256, /25=128), Subnet mask, Private IP ranges, NAT')
practice('GFG CN MCQs — DNS/TLS (10 Qs). Write DNS resolution steps from memory.')
section_tag('Evening Tasks')
bullet('DevOps: Monitoring for deployed project (uptime check + error alerting)')
bullet('Resume: Final pass — every bullet = action verb + quantified achievement')
divider()

# ── JUN 17 ──
date_header('JUNE 17 (TUE)')
section_tag('DSA: Fenwick Tree (BIT)  [1 day]')
bullet('BIT: 1-indexed, node i responsible for i & (-i) elements (lowest set bit)')
bullet('Prefix sum query: traverse i to 0 subtracting i & (-i)')
bullet('Point update: traverse i to n adding i & (-i)')
bullet('Build BIT O(n), 2D BIT basics, BIT vs Segment Tree comparison')
practice('CSES — Dynamic Range Sum. LeetCode #307, #315, #493 (Reverse Pairs).')
section_tag('CN: Day 5 — Load Balancing + CDN + Routing')
bullet('L4 LB: transport layer, routes by IP+port, fast')
bullet('L7 LB: application layer, routes by URL/header/cookie — Nginx, HAProxy')
bullet('Algorithms: Round Robin, Weighted RR, Least Connections, IP Hash')
bullet('Reverse proxy: hides origin, SSL termination, compression, caching')
bullet('CDN: edge servers, cache-control headers, TTL, invalidation strategies')
practice('Write "What happens when you type https://google.com?" — full walkthrough from scratch.')
section_tag('Evening Tasks')
bullet('Open Source: Follow up on all pending PRs — push for review/merge x4')
bullet('GitHub: Every repo needs description + topics + proper README')
divider()

# ── JUN 18 ──
date_header('JUNE 18 (WED)')
section_tag('DSA: Revision Day 1 — Arrays to BST Rapid-fire')
bullet('2 timed problems per topic: Two Pointers, Hashing, Sliding Window, Stacks, Queues')
bullet('Linked List, Binary Search, Recursion, Backtracking, Trees, BST')
bullet('Total ~22 problems, 90 min, no hints — note every slow/wrong area')
practice('LeetCode — filter by topic tag, medium, 2 per topic. Record accuracy per topic.')
section_tag('CN: Day 6 — CN Mock  →  CN COMPLETE')
bullet('30 interview Q&A spoken aloud (5 per: OSI, TCP, HTTP, DNS/TLS, LB, Subnetting)')
bullet('HTTP deep dive: status codes, methods, headers (Content-Type, Auth, Cache-Control)')
bullet('"What happens when you type a URL?" — verbal timed (under 3 min)')
bullet('Write CN cheat sheet (1 page: OSI, TCP handshake, DNS, TLS, HTTP versions)')
practice('InterviewBit CN mock. GFG CN Full Practice Set. Speak answers aloud.')
section_tag('Evening — CN COMPLETE')
bullet('Behavioral: Practice 3 STAR stories aloud with timer (90 sec per story)')
bullet('LinkedIn: Post 3 — open source contributions journey / lessons')
divider()

# ── JUN 19 ──
date_header('JUNE 19 (THU)')
section_tag('DSA: Revision Day 2 — Heap to Advanced Rapid-fire')
bullet('2 timed per topic: Heap, Greedy, Trie, Bit Manip, Graphs BFS/DFS')
bullet('Graphs Topo, Dijkstra, MST, DSU, Sorting, DP (all 5), Advanced Graphs, SegTree, BIT')
practice('LeetCode — 90 min, 2 mediums per topic. Codeforces — 1 graph problem.')
section_tag('OOP+LLD: Day 1 — OOP 4 Pillars')
bullet('Encapsulation: private fields, public getters/setters, data hiding')
bullet('Abstraction: abstract classes vs interfaces')
bullet('Inheritance: single, multilevel, multiple (Python MRO, Java interfaces)')
bullet('Polymorphism: compile-time (overloading), runtime (overriding)')
bullet('IS-A (inheritance) vs HAS-A (composition) — prefer composition')
practice('Write code examples for all 4 pillars in Python/Java. GFG OOP MCQs (10).')
section_tag('Evening Tasks')
bullet('HR: Record 2-min \'Tell me about yourself\' — listen back, refine')
bullet('Project: Practice 5-min architecture walkthrough aloud (draw on paper)')
divider()

# ── JUN 20 ──
date_header('JUNE 20 (FRI)')
section_tag('DSA: Revision Day 3 — Weak Topics Deep Dive')
bullet('From Revision Days 1+2, pick top 5 weakest topics (<70% accuracy)')
bullet('3 problems each on weak topics = 15 targeted problems, no time pressure')
bullet('Write pattern template for each weak topic')
practice('LeetCode — filter by weak topic tags, medium/hard. Read 1 solution discussion per topic.')
section_tag('OOP+LLD: Day 2 — SOLID Principles')
bullet('SRP: one class = one reason to change')
bullet('OCP: extend via new classes, don\'t modify existing code')
bullet('LSP: subclass substitutable for base (Square extending Rectangle breaks LSP)')
bullet('ISP: many small interfaces > one fat interface')
bullet('DIP: depend on abstractions not concretions; DRY, KISS, YAGNI')
practice('Find 5 SOLID violations in open source codebase. Write fixed versions.')
section_tag('Evening Tasks')
bullet('Resume: Print-read final version — action verb + achievement + metric per bullet')
bullet('LinkedIn: Ensure 3 posts published + profile headline updated')
divider()

# ── JUN 21 ──
date_header('JUNE 21 (SAT)')
section_tag('DSA: MOCK OA #2 (Full Simulation)')
bullet('2.5-hr timed OA — LeetCode virtual / Codeforces Div 2 virtual')
bullet('Full post-OA review: recode unsolved, classify by type')
practice('LeetCode Virtual Contest (past weekly). Codeforces virtual participation.')
section_tag('OOP+LLD: Day 3 — Design Patterns')
bullet('Creational: Singleton (thread-safe), Factory Method, Abstract Factory, Builder')
bullet('Structural: Adapter (wrap incompatible interface), Decorator (add behavior)')
bullet('Behavioral: Observer (pub-sub), Strategy (swap algorithms), Command, State, Template')
practice('Implement from scratch: Singleton (thread-safe) + Observer + Strategy. GFG MCQs (10).')
divider()

# ── JUN 22 ──
date_header('JUNE 22 (SUN)')
section_tag('DSA: Cross-Subject Revision — OS Quick Revision')
bullet('15 min each: Scheduling (Gantt), Deadlocks (Banker\'s), Memory (address translation)')
bullet('Virtual Memory (FIFO+LRU same ref string), IPC (identify use case)')
bullet('10 rapid-fire OS Q&A spoken aloud')
practice('GFG OS — 20 mixed MCQs. InterviewBit OS section.')
section_tag('OOP+LLD: Day 4 — LLD Design Sessions')
bullet('Interview approach: requirements → entities → relationships → interfaces → code')
bullet('Design #1: Parking Lot System (Vehicle hierarchy, ParkingSpot, ParkingLot, Ticket)')
bullet('Design #2: Tic Tac Toe (Board, Player, Game, WinChecker)')
practice('Code both designs from scratch. Explain class hierarchy aloud in 5 min each.')
section_tag('Evening — CONTEST')
bullet('LeetCode Weekly Contest')
divider()

# ── JUN 23 ──
date_header('JUNE 23 (MON)')
section_tag('DSA: Cross-Subject — DBMS Quick Revision')
bullet('15 min each: Normalization, Indexing, Transactions, Isolation levels')
bullet('Write 5 SQL queries cold (no notes)')
practice('GFG DBMS — 20 mixed MCQs. InterviewBit DBMS section.')
section_tag('OOP+LLD: Day 5 — More LLD Designs')
bullet('Design #3: Snake Game (Grid, Snake, Food, Direction, GameState)')
bullet('Design #4: Splitwise (User, Group, Expense, Split types: equal/exact/percent)')
practice('Code both designs from scratch. Draw class diagrams first.')
section_tag('Evening Tasks')
bullet('Behavioral: Write STAR story #3 — teamwork experience')
bullet('HR: Practice project deep-dive aloud (5 min: architecture, decisions, tradeoffs)')
divider()

# ── JUN 24 ──
date_header('JUNE 24 (TUE)')
section_tag('DSA: Cross-Subject — CN + OOP Quick Revision')
bullet('CN: TCP handshake, HTTP versions, DNS, TLS — 10 rapid-fire Q&A')
bullet('OOP: Write Singleton + Observer from scratch, explain 3 SOLID violations')
practice('GFG CN + OOP — 20 mixed MCQs. InterviewBit CN section.')
section_tag('OOP+LLD: Day 6 — Final LLD + Mock  →  LLD COMPLETE')
bullet('Design #5: Elevator System (Elevator, ElevatorController, Request, Direction, Strategy)')
bullet('Design #6: Vending Machine (State pattern: Idle, HasMoney, Dispensing)')
bullet('Full OOP/LLD revision: explain any design aloud in 5 min')
practice('Explain all 6 LLD designs from memory — diagram + core logic. Time: 30 min total.')
section_tag('Evening — LLD COMPLETE')
bullet('Behavioral: Write STAR story #4 — failure + what you learned')
divider()

# ── JUN 25 ──
date_header('JUNE 25 (WED)')
section_tag('DSA: Core Mock Exam')
bullet('40 mixed questions (10 per subject: OS, DBMS, CN, OOP) — timed 60 min')
bullet('Grade + identify weak areas below 70%')
practice('GFG mock tests — all 4 subjects. InterviewBit mixed practice.')
section_tag('HLD: Day 1 — Fundamentals')
bullet('CAP theorem (Consistency, Availability, Partition tolerance — pick 2)')
bullet('Caching strategies: cache-aside, write-through, write-behind, TTL')
bullet('Load Balancing: L4 vs L7, algorithms, health checks')
bullet('Sharding: horizontal vs vertical, consistent hashing, shard key selection')
practice('Read: Grokking System Design (chapters 1-3). Explain CAP aloud with examples.')
section_tag('Evening Tasks')
bullet('Gap filling: re-study topics scored below 70% in mock')
bullet('Open Source: Status check on all LiteLLM PRs — push for merge')
divider()

# ── JUN 26 ──
date_header('JUNE 26 (THU)')
section_tag('DSA: Weak Topic Deep Practice')
bullet('Revisit all problem patterns where accuracy < 70%')
bullet('5 focused problems on top 3 weakest areas')
practice('LeetCode — targeted by topic tag. No time limit, understand patterns.')
section_tag('HLD: Day 2 — Architecture Patterns')
bullet('Replication: master-slave, master-master, sync vs async')
bullet('Microservices vs Monolith (when to split, tradeoffs)')
bullet('API Gateway: routing, auth, rate limiting, aggregation')
bullet('Message Queues: Kafka vs RabbitMQ, pub-sub vs point-to-point, at-most/at-least/exactly-once')
bullet('SQL vs NoSQL: when to use each (ACID vs BASE, schema flexibility)')
practice('Read: Grokking System Design (chapters 4-6). Draw microservices architecture for project.')
section_tag('Evening Tasks')
bullet('Resume: Print-read — is this resume ready for a recruiter? Final polish.')
divider()

# ── JUN 27 ──
date_header('JUNE 27 (FRI)')
section_tag('DSA: Mixed Practice — All Topics')
bullet('10 LC mediums (random pick across all topics, timed 90 min)')
practice('LeetCode random medium. Codeforces — 1 problem.')
section_tag('HLD: Day 3 — System Design Problems')
bullet('Design URL Shortener: hash function, Base62, read-heavy caching, TTL')
bullet('Design Rate Limiter: token bucket, sliding window, distributed (Redis)')
bullet('Design Notification System: push/pull, pub-sub, priority queue')
practice('Grokking System Design — URL Shortener + Rate Limiter chapters. Draw architecture from scratch.')
section_tag('Evening Tasks')
bullet('Behavioral: Practice all 4 STAR stories aloud (90 sec each)')
bullet('Mock DSA Interview prep: review approach framework (read → think → explain → code → test)')
divider()

# ── JUN 28 ──
date_header('JUNE 28 (SAT)')
section_tag('DSA: MOCK OA #3')
bullet('2.5-hr timed OA — LeetCode virtual contest')
bullet('Full post-OA review + pattern classification')
practice('LeetCode Virtual Contest.')
section_tag('HLD: Day 4 — More Designs + Revision')
bullet('Design Uber-like: real-time location (WebSocket), matching, pricing, map')
bullet('Full HLD revision: CAP, caching, sharding, replication, message queues')
practice('Explain URL Shortener + Rate Limiter + Uber aloud (5 min each). Draw architecture from memory.')
section_tag('Evening Tasks')
bullet('Week 5 recap: all core subjects done, all DSA topics done, HLD light done')
bullet('Mock Interview #1 tomorrow')
divider()

# ══════════════════════════════════════════════════════════
# PHASE 2: PLACEMENT SPRINT (June 29 – July 31)
# ══════════════════════════════════════════════════════════

phase_header('═══  PHASE 2 — PLACEMENT SPRINT  (June 29 – July 31)  ═══')
add_line('All DSA topics covered. All core subjects mastered. Now: OA grind, mocks, profile polish.', bold=True, size=9, color=RGBColor(0xC0,0x00,0x00))

# ── WEEK 7: Jun 29 - Jul 5 ──
phase_header('WEEK 7 — MASS OA PREP + GAP FILLING  (Jun 29 - Jul 5)')

date_header('JUNE 29 (SUN)')
section_tag('Mock DSA Interview #1')
bullet('Platform: Pramp.com (free, peer-to-peer) — 45 min DSA (2 problems, think aloud)')
bullet('Review feedback immediately — note every weakness')
section_tag('OA Grind')
bullet('5 timed OA problems (LeetCode medium, 15 min each)')
bullet('LeetCode Weekly Contest (Sunday mandatory)')
practice('Pramp.com for mock. LeetCode contest. PrepInsta for service company OA patterns.')
divider()

date_header('JUNE 30 (MON) - JULY 1 (TUE)')
section_tag('Mass OA Grind — Service Companies')
bullet('Jun 30: 5 OA problems (2 medium + 1 hard) + OS rapid-fire revision (20 Q&A)')
bullet('Jul 1: 5 OA problems (2 medium + 1 hard) + DBMS rapid-fire revision (20 Q&A)')
bullet('Focus: pattern recognition speed — identify problem type in <2 min')
practice('LeetCode — daily challenge + 4 more. PrepInsta — TCS, Infosys, Wipro, Cognizant patterns.')
section_tag('Evening Tasks')
bullet('Project architecture diagram — clean version for interviews')
bullet('DevOps: Verify all CI/CD + Docker + deployment is working')
divider()

date_header('JULY 2 (WED) - JULY 3 (THU)')
section_tag('OA Grind + Mock Interview #2')
bullet('Jul 2: 5 OA problems + CN rapid-fire revision (20 Q&A)')
bullet('Jul 3: Mock DSA Interview #2 (Pramp.com / interviewing.io) — show improvement from Mock #1')
bullet('3 STAR stories: challenge, conflict, teamwork — practice aloud')
practice('Pramp.com / interviewing.io for mock. LeetCode 5 problems/day.')
section_tag('Evening Tasks')
bullet('Resume: Final metrics pass — every number is accurate')
bullet('LinkedIn: Ensure all 3 posts visible + connections with recruiters')
divider()

date_header('JULY 4 (FRI) - JULY 5 (SAT)')
section_tag('OA Grind + HLD Refresh')
bullet('Jul 4: 5 OA problems + OOP/LLD rapid-fire (explain 3 designs from memory)')
bullet('Jul 5: 5 OA problems + HLD: CAP + URL Shortener + Rate Limiter rapid refresh')
bullet('LeetCode Virtual Contest (timed 2.5 hrs)')
practice('LeetCode 5 problems/day. Codeforces virtual Div 2.')
divider()

# ── WEEK 8: Jul 6 - Jul 12 ──
phase_header('WEEK 8 — PRODUCT COMPANY OA + MOCK DSA + HR  (Jul 6 - Jul 12)')

date_header('JULY 6 (SUN) - JULY 8 (TUE)')
section_tag('Product Company OA Level')
bullet('Jul 6: 5 problems (1 hard) + LeetCode Weekly Contest')
bullet('Jul 7: 5 problems (1 hard) + OS targeted revision (weakest areas only)')
bullet('Jul 8: Mock DSA Interview #3 (Pramp.com / interviewing.io)')
practice('LeetCode — company-tagged problems (Google, Amazon, Microsoft). 1 hard/day mandatory.')
section_tag('Evening Tasks')
bullet('HR stories: leadership, conflict, failure, teamwork — 4 stories polished')
bullet('Resume metrics: every bullet = action verb + achievement + number')
divider()

date_header('JULY 9 (WED) - JULY 12 (SAT)')
section_tag('Continued OA Grind + Subject Refresh')
bullet('Jul 9: 5 problems (1 hard) + DBMS targeted (weakest SQL patterns)')
bullet('Jul 10: 5 problems (1 hard) + CN targeted (HTTP, DNS, TLS)')
bullet('Jul 11: 5 problems (1 hard) + OOP/LLD targeted (weakest designs)')
bullet('Jul 12: MOCK OA #4 — Full 2.5-hr timed (LeetCode virtual)')
practice('LeetCode company tags + contest. Codeforces Div 2 virtual.')
section_tag('Evening Tasks')
bullet('Open Source: target 2 of 4 LiteLLM PRs merged — follow up aggressively')
bullet('Raise 1 more PR if previous ones stalled (docs, test, small bug fix)')
divider()

# ── WEEK 9: Jul 13 - Jul 19 ──
phase_header('WEEK 9 — HARD PROBLEMS + FULL MOCK INTERVIEWS  (Jul 13 - Jul 19)')

date_header('JULY 13 (SUN) - JULY 14 (MON)')
section_tag('Hard Problem Focus')
bullet('Jul 13: LeetCode Weekly Contest + 3 hard problems (DP + Graph)')
bullet('Jul 14: 3 hard problems (Tree DP, Graph DP, Segment Tree)')
bullet('Open Source: follow up on all LiteLLM PRs')
practice('LeetCode hard filter. Codeforces Div 1 C/D problems.')
divider()

date_header('JULY 15 (TUE)')
section_tag('Full Mock Interview #1')
bullet('Format: DSA 45 min (2 problems, think aloud) + CS 20 min (OS/DBMS/CN rapid) + Project 15 min')
bullet('Platform: Pramp.com / interviewing.io / ask CS friend to mock you')
bullet('Review feedback immediately — note every weakness')
divider()

date_header('JULY 16 (WED) - JULY 17 (THU)')
section_tag('Hard Problems Continued')
bullet('Jul 16: String hard (regex matching, wildcard, KMP pattern)')
bullet('Jul 17: DBMS SQL hard (LeetCode SQL hard: 5 problems)')
bullet('Jul 17: Mixed hard from personal weak list')
practice('LeetCode hard filter. Note: understand solution even if you can\'t solve it.')
divider()

date_header('JULY 18 (FRI)')
section_tag('Full Mock Interview #2')
bullet('Same format as Mock #1 — show improvement')
bullet('Project walkthrough: 5-min architecture, answer 3 deep-dive questions')
divider()

date_header('JULY 19 (SAT)')
section_tag('Codeforces Contest + Project Deep-Dive')
bullet('Live Codeforces Div 2 OR virtual — compete under real conditions')
bullet('Post-contest: solve all unfinished (editorial → code from scratch)')
bullet('Project deep-dive solo: 5-min architecture walkthrough aloud until seamless')
practice('Codeforces.com contests. LeetCode biweekly contest.')
divider()

# ── WEEK 10: Jul 20 - Jul 26 ──
phase_header('WEEK 10 — FULL REVISION + PROFILE FINAL POLISH  (Jul 20 - Jul 26)')

date_header('JULY 20 (SUN) - JULY 21 (MON)')
section_tag('DSA Full Revision — 2 Problems Per Topic (All 22 Topics)')
bullet('Jul 20: Topics 1-11 — Arrays, Two Pointers, Hashing, Sliding Window, Stack, Queue, LL, BS, Recursion, Backtracking, Trees')
bullet('Jul 21: Topics 12-22 — BST, Heap, Greedy, Trie, Bit Manip, Graphs, DSU, Sorting, DP, Adv Graphs, SegTree, BIT')
bullet('2 problems × 22 topics = ~44 problems over 2 days (timed, medium)')
practice('LeetCode — topic filter. Record accuracy per topic. Identify final weak areas.')
section_tag('20 Most-Asked CS Q Per Subject')
bullet('Jul 21: OS (20 Qs): Process vs thread, Deadlock, Paging vs seg, Semaphore vs mutex, Page replacement')
bullet('Jul 21: DBMS (20 Qs): Normalization, ACID, Isolation, B-tree vs hash, MVCC, VACUUM')
practice('Speak all Q&A aloud — not written. Writing too slow for interview warm-up.')
divider()

date_header('JULY 22 (TUE)')
section_tag('Full Mock Interview #3')
bullet('Format: DSA 45 min + CS 20 min (all 4 subjects) + Project 15 min + HR 10 min')
bullet('This is FINAL practice full interview — treat as real')
bullet('Record if possible — review communication, approach clarity, time management')
section_tag('20 Most-Asked CS Q continued')
bullet('CN (20 Qs): OSI, TCP vs UDP, HTTP/1.1 vs 2, DNS, TLS, REST')
bullet('OOP (20 Qs): SOLID, design patterns (when to use), 4 pillars, composition vs inheritance')
practice('Speak all Q&A aloud.')
divider()

date_header('JULY 23 (WED) - JULY 24 (THU)')
section_tag('Resume + LinkedIn Final Polish + OA Simulations')
bullet('Jul 23: Resume print-read — every line correct, one page, no passive voice')
bullet('Jul 24: LinkedIn — complete profile, 3 posts visible, project with demo link, connect recruiters')
bullet('Jul 24: LeetCode virtual contest (2.5 hrs, strict timer)')
practice('LeetCode virtual contest (timed).')
divider()

date_header('JULY 25 (FRI)')
section_tag('HR Mock + OA Simulation')
bullet('HR Mock: 10 behavioral questions — record on phone, listen back')
bullet('Questions: Tell me about yourself / Greatest challenge / Team conflict / Failure / 5-year plan')
bullet('Strengths / Why SDE / Why this company / Achievement / Leadership')
bullet('Codeforces Div 2 virtual (2.5 hrs)')
practice('Codeforces virtual. HR questions spoken aloud, timed.')
divider()

date_header('JULY 26 (SAT)')
section_tag('Profile Final Polish')
bullet('Resume: Print-read final — if you\'d hand to recruiter, it\'s done')
bullet('LinkedIn: Profile strength = All-Star, skills endorsed, project post with demo')
bullet('GitHub: Contribution graph consistent, pinned repos strong, profile README complete')
bullet('Open Source: total 2-5 contributions visible (merged or raised PRs)')
divider()

# ── WEEKS 11-12: Jul 27 - Jul 31 ──
phase_header('═══  FINAL MODE — FULL INTERVIEW MODE  (Jul 27 - Jul 31)  ═══')

add_line('MANDATORY DAILY ROUTINE:', bold=True, color=RGBColor(0xC0,0x00,0x00))
add_line('  Morning: 2.5-hr timed OA (LeetCode virtual / Codeforces virtual)', size=9)
add_line('  Afternoon: Core CS rapid-fire warmup (15 min — 5 Qs per subject, spoken aloud)', size=9)
add_line('  Evening: HR mock / Project deep-dive / 2-min resume walkthrough', size=9)

date_header('JULY 27 (SUN)')
bullet('Timed OA (2.5 hrs) — LeetCode virtual contest')
bullet('HR mock: 5 behavioral + project deep-dive (30 min)')
bullet('LeetCode Weekly Contest (Sunday mandatory)')
divider()

date_header('JULY 28 (MON)')
bullet('Timed OA (2.5 hrs) — LeetCode virtual')
bullet('2-min resume walkthrough: speak aloud 5× until seamless')
bullet('Core CS rapid-fire: 20 Qs (5 each: OS, DBMS, CN, OOP) spoken aloud')
divider()

date_header('JULY 29 (TUE)')
bullet('Timed OA (2.5 hrs) — Codeforces virtual Div 2')
bullet('HR mock: all 4 STAR stories + \'Tell me about yourself\' (timed, 10 min)')
bullet('Project Q&A deep-dive: explain every design decision, tradeoff, improvement')
divider()

date_header('JULY 30 (WED)')
bullet('Timed OA (2.5 hrs) — LeetCode virtual')
bullet('Core CS rapid-fire: focus on personal weak areas from mocks')
bullet('\'Tell me about yourself\' spoken 10× (non-negotiable — should be automatic)')
divider()

date_header('JULY 31 (THU) — TARGET DATE')
bullet('Final Timed OA (2.5 hrs)')
bullet('Core CS rapid-fire warmup (15 min)')
bullet('Resume walkthrough: one final read')
bullet('\'Tell me about yourself\' — speak aloud one final time')
add_line('', size=5)
add_heading_text('═══  PLACEMENT READY — JULY 31, 2026  ✓  ═══', size=14, align=WD_ALIGN_PARAGRAPH.CENTER, color=RGBColor(0x37,0x56,0x23))

# ══════════════════════════════════════════════════════════
# QUICK REFERENCE SECTIONS
# ══════════════════════════════════════════════════════════

doc.add_page_break()
add_heading_text('QUICK REFERENCE — SUMMARY TABLES', size=14)

# Contest Schedule
add_heading_text('Contest Schedule (Every Sunday — Non-Negotiable)', size=11)
for c in [
    'May 25, Jun 1, Jun 8, Jun 15, Jun 22, Jun 29, Jul 6, Jul 13, Jul 20, Jul 27',
    'Platform: LeetCode Weekly Contest (primary), Codeforces Div 2 (alternate)',
    'Post-contest: read editorial for every unsolved, recode from scratch'
]:
    add_line(f'  • {c}', size=9)

# Mock Interview Schedule
add_heading_text('Mock Interview Schedule', size=11)
for m in [
    'Mock DSA #1: June 29 (Pramp.com)',
    'Mock DSA #2: July 3 (Pramp.com / interviewing.io)',
    'Mock DSA #3: July 8 (Pramp.com / interviewing.io)',
    'Full Mock #1: July 15 (DSA 45 + CS 20 + Project 15 min)',
    'Full Mock #2: July 18 (same format)',
    'Full Mock #3: July 22 (DSA 45 + CS 20 + Project 15 + HR 10 min)'
]:
    add_line(f'  • {m}', size=9)

# Practice Platforms
add_heading_text('Practice Platforms', size=11)
for p in [
    'DSA: LeetCode (primary), Codeforces (contests), CSES (Segment Tree/BIT)',
    'OS/DBMS/CN/OOP: GFG Practice Sets, InterviewBit, GFG MCQs',
    'SQL: LeetCode SQL section (medium+hard), HackerRank SQL',
    'Mock OAs: LeetCode Virtual Contest, Codeforces Virtual, PrepInsta (service companies)',
    'Mock Interviews: Pramp.com (free, peer), interviewing.io (free tier), peer mock'
]:
    add_line(f'  • {p}', size=9)

# Open Source
add_heading_text('Open Source Tracking', size=11)
for o in [
    'LiteLLM: 4 PRs raised → follow up weekly, push for merge',
    'Target: 2-5 total contributions visible by July 31',
    'Issues: github.com/BerriAI/litellm/issues (filter: good first issue)',
    'Weekly check-ins: May 27, Jun 5, Jun 13, Jun 17, Jun 25, Jul 12'
]:
    add_line(f'  • {o}', size=9)

# Subject Completion Timeline
add_heading_text('Subject Completion Timeline', size=11)
for s in [
    'OS: May 24-31 (8 days) → Processes, Threads, Scheduling, Sync, Deadlocks, Memory, VM, FS+IPC',
    'DBMS: Jun 1-12 (12 days) → ER, Normalization, SQL, Indexing, Transactions, Concurrency, PG Internals',
    'CN: Jun 13-18 (6 days) → OSI, TCP/UDP, HTTP/REST, DNS/TLS, LB/CDN',
    'OOP+LLD: Jun 19-24 (6 days) → 4 Pillars, SOLID, Design Patterns, 6 LLD Designs',
    'HLD: Jun 25-28 (4 days) → CAP, Caching, LB, Sharding, MQ, Designs (URL Shortener, Rate Limiter, Uber)'
]:
    add_line(f'  • {s}', size=8.5)

# Remaining DSA Topics
add_heading_text('Remaining DSA Topics — 17 Groups', size=11)
for t in [
    'Two Pointers + Hashing (May 24)',
    'Recursion (May 25), Backtracking (May 26)',
    'Binary Trees Pt 1+2 (May 27-28), BST (May 29)',
    'Heap/PQ (May 30), Greedy (Jun 1), Trie (Jun 2)',
    'Bit Manipulation + OA Math (Jun 3)',
    'Graphs: BFS+DFS (Jun 4), Cycle+Topo (Jun 5), Shortest Path (Jun 6), MST+DSU (Jun 7)',
    'Sorting Algorithms (Jun 8)',
    'DP: 1D (Jun 9), 2D/Grid (Jun 10), Knapsack (Jun 11), String DP (Jun 12), Advanced (Jun 13)',
    'Advanced Graphs: Bridges+SCC (Jun 15)',
    'Segment Tree (Jun 16), Fenwick Tree/BIT (Jun 17)'
]:
    add_line(f'  • {t}', size=8.5)

# Final Output
add_heading_text('FINAL OUTPUT BY JULY 31, 2026', size=11, color=RGBColor(0x37,0x56,0x23))
for f in [
    '950+ LeetCode problems solved',
    'All 22 DSA topics — interview fluency',
    'OS, DBMS, CN, OOP — isolated and mastered',
    '1 deployed AI-powered production project (DONE)',
    'CI/CD + Docker + Nginx + VPS live',
    '6 LLD designs implemented and explainable',
    'HLD awareness: URL Shortener, Rate Limiter, Notification, Uber',
    '6 mock interviews completed (3 DSA + 3 full)',
    'Resume with quantified action-verb bullets',
    'LinkedIn with project demo + 3 architecture posts',
    '2-5 open source contributions (LiteLLM)',
    'HR stories ready in polished STAR format (4 stories)',
    'Portfolio — complete (DONE)'
]:
    add_line(f'  ✓ {f}', size=9, color=RGBColor(0x37,0x56,0x23))

# ── Save ──
parser = argparse.ArgumentParser(description='Generate the roadmap docx file.')
parser.add_argument(
    '-o',
    '--output',
    default='REMAINING_ROADMAP_May24_Jul31.docx',
    help='Output .docx path (default: REMAINING_ROADMAP_May24_Jul31.docx).'
)
args = parser.parse_args()

target_path = os.path.abspath(args.output)
target_dir = os.path.dirname(target_path) or os.getcwd()

try:
    os.makedirs(target_dir, exist_ok=True)
except OSError as exc:
    print(f'✗ Failed to create output directory: {target_dir} ({exc})', file=sys.stderr)
    sys.exit(1)

if not os.access(target_dir, os.W_OK):
    print(f'✗ Output directory not writable: {target_dir}', file=sys.stderr)
    sys.exit(1)

try:
    doc.save(target_path)
except Exception as exc:
    print(f'✗ Failed to save document: {exc}', file=sys.stderr)
    sys.exit(1)

print(f'✓ Saved to: {target_path}')
