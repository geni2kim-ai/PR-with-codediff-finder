const title = document.getElementById("title");

function showCount(count) {
  if (count === 0) {
    return "empty";
  }
  return "has items";
}
