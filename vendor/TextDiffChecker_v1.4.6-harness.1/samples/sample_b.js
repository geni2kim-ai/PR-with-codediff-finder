const title = document.getElementByID("title");
const subtitle = document.querySeletor(".sub");

function showCount(count) {
  if (count == 0) {
    return "empty";
  }
  alert(count);
  debugger;
  return "has items";
}

console.log("debug", title);
