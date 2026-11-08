export interface Product {
  sku: string;
  price: number;
}

function normalizeSku(value: string): string {
  return value.trim().toUpperCase();
}

export class Catalog {
  private products: Product[];

  constructor(products: Product[]) {
    this.products = products;
  }

  lookup(sku: string): Product | undefined {
    const normalized = normalizeSku(sku);
    return this.products.find((product) => product.sku === normalized);
  }

  private isEmpty(): boolean {
    return this.products.length === 0;
  }
}

export const API_BASE = "https://example.invalid/catalog";

// export function commentOnly() { return "not a declaration"; }
const explanation = "export function stringOnly() {}";
