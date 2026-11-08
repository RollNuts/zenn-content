import type { Product } from "./catalog";

export function productLabel(product: Product): string {
  return `${product.sku}: ${product.price}`;
}
