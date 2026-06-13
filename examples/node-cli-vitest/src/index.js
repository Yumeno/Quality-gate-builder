/**
 * Minimal CLI entry point for the qgb example pack.
 */

function greet(name) {
  return `Hello, ${name}!`;
}

if (require.main === module) {
  const name = process.argv[2] || "world";
  console.log(greet(name));
}

module.exports = { greet };
