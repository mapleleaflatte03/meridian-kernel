#!/usr/bin/env python3
"""
Revenue operating layer — clients, orders, receivables.
State machine: proposed -> accepted -> in_progress -> delivered -> invoiced -> paid
Owner draws, reimbursements, and capital contributions are deployment-specific
treasury actions handled outside this revenue module.

Usage:
  python3 revenue.py client add --name "Client Name" --contact "email or chat"
  python3 revenue.py client list
  python3 revenue.py order create --client <id> --product <product> --amount <usd> [--note "..."]
  python3 revenue.py order advance <order_id>
  python3 revenue.py order reject <order_id> --note "reason"
  python3 revenue.py order list [--status <status>]
  python3 revenue.py order show <order_id>
  python3 revenue.py summary
"""
import json, os, sys, argparse, datetime, uuid

ECONOMY_DIR  = os.path.dirname(os.path.abspath(__file__))
REVENUE_FILE = os.path.join(ECONOMY_DIR, 'revenue.json')
LEDGER       = os.path.join(ECONOMY_DIR, 'ledger.json')
TRANSACTIONS = os.path.join(ECONOMY_DIR, 'transactions.jsonl')

ORDER_STATES = ['proposed', 'accepted', 'in_progress', 'delivered', 'invoiced', 'paid']
ADVANCE_MAP  = {s: ORDER_STATES[i+1] for i, s in enumerate(ORDER_STATES[:-1])}

def now_ts():
    return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

def load_revenue():
    if os.path.exists(REVENUE_FILE):
        with open(REVENUE_FILE) as f:
            return json.load(f)
    return {'clients': {}, 'orders': {}, 'receivables_usd': 0.0, 'updatedAt': now_ts()}

def save_revenue(data):
    data['updatedAt'] = now_ts()
    with open(REVENUE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_ledger():
    with open(LEDGER) as f:
        return json.load(f)

def save_ledger(data):
    data['updatedAt'] = now_ts()
    with open(LEDGER, 'w') as f:
        json.dump(data, f, indent=2)

def append_tx(entry):
    entry['ts'] = now_ts()
    with open(TRANSACTIONS, 'a') as f:
        f.write(json.dumps(entry) + '\n')

# ── Client management ────────────────────────────────────────────────────────

def cmd_client_add(args):
    data = load_revenue()
    cid = str(uuid.uuid4())[:8]
    data['clients'][cid] = {
        'name': args.name,
        'contact': args.contact,
        'created_at': now_ts(),
    }
    save_revenue(data)
    print(f"Client added: {cid} ({args.name})")

def cmd_client_list(args):
    data = load_revenue()
    if not data['clients']:
        print("No clients registered.")
        return
    for cid, c in data['clients'].items():
        print(f"  {cid}  {c['name']:<30} {c.get('contact','')}")

# ── Order state machine ──────────────────────────────────────────────────────

def cmd_order_create(args):
    data = load_revenue()
    if args.client not in data['clients']:
        print(f"ERROR: unknown client '{args.client}'"); return
    oid = str(uuid.uuid4())[:8]
    data['orders'][oid] = {
        'client':     args.client,
        'product':    args.product,
        'amount_usd': float(args.amount),
        'status':     'proposed',
        'note':       args.note or '',
        'history':    [{'status': 'proposed', 'at': now_ts()}],
        'created_at': now_ts(),
    }
    data['receivables_usd'] += float(args.amount)
    save_revenue(data)
    append_tx({'type': 'order_created', 'order_id': oid, 'amount': float(args.amount),
               'client': args.client, 'product': args.product})
    print(f"Order created: {oid} (${args.amount} — {args.product})")

def cmd_order_advance(args):
    data = load_revenue()
    oid = args.order_id
    if oid not in data['orders']:
        print(f"ERROR: unknown order '{oid}'"); return
    order = data['orders'][oid]
    cur = order['status']
    if cur not in ADVANCE_MAP:
        print(f"ERROR: order '{oid}' is already in terminal state '{cur}'"); return
    nxt = ADVANCE_MAP[cur]
    order['status'] = nxt
    order['history'].append({'status': nxt, 'at': now_ts()})

    # When status becomes 'paid', credit treasury
    if nxt == 'paid':
        ledger = load_ledger()
        amount = order['amount_usd']
        ledger['treasury']['cash_usd'] += amount
        ledger['treasury']['total_revenue_usd'] = ledger['treasury'].get('total_revenue_usd', 0) + amount
        save_ledger(ledger)
        data['receivables_usd'] = max(0, data['receivables_usd'] - amount)
        append_tx({'type': 'customer_payment', 'order_id': oid, 'amount': amount,
                   'client': order['client'], 'product': order['product'],
                   'note': f"Order {oid} paid — treasury credited"})
        print(f"PAID: ${amount} credited to treasury. Order {oid} complete.")
    else:
        append_tx({'type': 'order_advanced', 'order_id': oid,
                   'from': cur, 'to': nxt})
        print(f"Order {oid}: {cur} → {nxt}")

    save_revenue(data)

def cmd_order_reject(args):
    data = load_revenue()
    oid = args.order_id
    if oid not in data['orders']:
        print(f"ERROR: unknown order '{oid}'"); return
    order = data['orders'][oid]
    order['status'] = 'rejected'
    order['history'].append({'status': 'rejected', 'at': now_ts(), 'note': args.note})
    data['receivables_usd'] = max(0, data['receivables_usd'] - order['amount_usd'])
    save_revenue(data)
    append_tx({'type': 'order_rejected', 'order_id': oid, 'note': args.note})
    print(f"Order {oid}: REJECTED — {args.note}")

def cmd_order_list(args):
    data = load_revenue()
    if not data['orders']:
        print("No orders."); return
    for oid, o in data['orders'].items():
        if args.status and o['status'] != args.status:
            continue
        cname = data['clients'].get(o['client'], {}).get('name', '?')
        print(f"  {oid}  ${o['amount_usd']:<10.2f} {o['status']:<14} {o['product']:<30} client={cname}")

def cmd_order_show(args):
    data = load_revenue()
    if args.order_id not in data['orders']:
        print(f"ERROR: unknown order '{args.order_id}'"); return
    o = data['orders'][args.order_id]
    cname = data['clients'].get(o['client'], {}).get('name', '?')
    print(json.dumps({**o, 'id': args.order_id, 'client_name': cname}, indent=2))

# ── Summary ──────────────────────────────────────────────────────────────────
# NOTE: Owner draws, reimbursements, and capital contributions are handled by
#       deployment-specific accounting workflows. This file handles revenue
#       operations only (clients, orders, receivables).

def cmd_summary(args):
    data = load_revenue()
    ledger = load_ledger()
    t = ledger['treasury']
    orders = data.get('orders', {})
    n_by_status = {}
    for o in orders.values():
        n_by_status[o['status']] = n_by_status.get(o['status'], 0) + 1

    print(f"\n=== Revenue Summary ===")
    print(f"Treasury cash:       ${t['cash_usd']:.2f}")
    print(f"Total revenue:       ${t.get('total_revenue_usd', 0):.2f}")
    print(f"Owner capital in:    ${t.get('owner_capital_contributed_usd', 0):.2f}")
    print(f"Owner draws:         ${t.get('owner_draws_usd', 0):.2f}")
    print(f"  (Owner draw/reimburse breakdown: deployment-specific accounting workflow)")
    print(f"Reserve floor:       ${t.get('reserve_floor_usd', 50):.2f}")
    print(f"Receivables:         ${data.get('receivables_usd', 0):.2f}")
    print(f"Clients:             {len(data.get('clients', {}))}")
    print(f"Orders:              {len(orders)}")
    for status, count in sorted(n_by_status.items()):
        print(f"  {status}: {count}")

# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description='Revenue operating layer')
    sub = p.add_subparsers(dest='command')

    # client
    csub = sub.add_parser('client').add_subparsers(dest='client_cmd')
    ca = csub.add_parser('add')
    ca.add_argument('--name', required=True)
    ca.add_argument('--contact', default='')
    csub.add_parser('list')

    # order
    osub = sub.add_parser('order').add_subparsers(dest='order_cmd')
    oc = osub.add_parser('create')
    oc.add_argument('--client', required=True)
    oc.add_argument('--product', required=True)
    oc.add_argument('--amount', required=True)
    oc.add_argument('--note', default='')
    oa = osub.add_parser('advance')
    oa.add_argument('order_id')
    orj = osub.add_parser('reject')
    orj.add_argument('order_id')
    orj.add_argument('--note', default='rejected')
    ol = osub.add_parser('list')
    ol.add_argument('--status', default=None)
    osh = osub.add_parser('show')
    osh.add_argument('order_id')

    sub.add_parser('summary')

    args = p.parse_args()
    if   args.command == 'client':
        if   args.client_cmd == 'add':  cmd_client_add(args)
        elif args.client_cmd == 'list': cmd_client_list(args)
        else: p.print_help()
    elif args.command == 'order':
        if   args.order_cmd == 'create':  cmd_order_create(args)
        elif args.order_cmd == 'advance': cmd_order_advance(args)
        elif args.order_cmd == 'reject':  cmd_order_reject(args)
        elif args.order_cmd == 'list':    cmd_order_list(args)
        elif args.order_cmd == 'show':    cmd_order_show(args)
        else: p.print_help()
    elif args.command == 'summary':
        cmd_summary(args)
    else:
        p.print_help()

if __name__ == '__main__':
    main()
